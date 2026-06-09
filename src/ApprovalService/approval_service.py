import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Event, Lock
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.data.tables import TableServiceClient, UpdateMode
from azure.core.exceptions import HttpResponseError, ResourceExistsError
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

load_dotenv()


@dataclass
class ApprovalDecision:
    approved: bool
    reason: str
    decision_id: str


class ApprovalRequest(BaseModel):
    function_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str = Field(min_length=1)


class ApprovalResponse(BaseModel):
    approved: bool
    reason: str
    decision_id: str


class ManualDecisionRequest(BaseModel):
  function_name: str = Field(default="issue_refund", min_length=1)
  arguments: dict[str, Any] = Field(default_factory=dict)
  correlation_id: str = Field(min_length=1)
  approved: bool
  reason: str = Field(min_length=1)


class PendingDecisionRequest(BaseModel):
  approved: bool
  reason: str = Field(min_length=1)


@dataclass
class PendingApproval:
  request: ApprovalRequest
  created_at: str
  event: Event
  decision: ApprovalDecision | None = None


class TableAuditStore:
  def __init__(self, table_service: TableServiceClient, table_name: str) -> None:
    self._service = table_service
    self._table_name = table_name
    try:
      self._service.create_table(table_name)
    except ResourceExistsError:
      pass
    self._table = self._service.get_table_client(table_name)

  def save_decision(self, request: ApprovalRequest, decision: ApprovalDecision, source: str = "rule") -> None:
    now = datetime.now(UTC)
    partition = now.strftime("%Y%m%d")
    order_id = str(request.arguments.get("order_id", ""))
    amount = request.arguments.get("amount", 0)
    entity = {
      "PartitionKey": partition,
      "RowKey": request.correlation_id,
      "function_name": request.function_name,
      "order_id": order_id,
      "amount": float(amount),
      "approved": decision.approved,
      "reason": decision.reason,
      "decision_id": decision.decision_id,
      "correlation_id": request.correlation_id,
      "source": source,
      "created_at": now.isoformat(),
    }
    self._table.upsert_entity(entity=entity, mode=UpdateMode.REPLACE)

  def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
    entities = list(self._table.list_entities(results_per_page=limit))
    entities.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return entities[:limit]


app = FastAPI(title="SupportAgent Approval Service")
PENDING_APPROVALS: dict[str, PendingApproval] = {}
PENDING_APPROVALS_LOCK = Lock()


def _validate_api_key(x_approval_key: str | None) -> None:
    required_key = os.getenv("APPROVAL_SERVICE_API_KEY", "").strip()
    if required_key and x_approval_key != required_key:
        raise HTTPException(status_code=401, detail="Invalid approval API key")


def _decide(request: ApprovalRequest) -> ApprovalDecision:
    threshold = float(os.getenv("APPROVAL_RULE_THRESHOLD", "1000"))
    amount = float(request.arguments.get("amount", 0))
    decision_id = f"decision_{uuid.uuid4().hex[:12]}"

    if amount > threshold:
        return ApprovalDecision(
            approved=False,
            reason=f"Amount ${amount:.2f} exceeds auto-approval threshold ${threshold:.2f}.",
            decision_id=decision_id,
        )

    return ApprovalDecision(
        approved=True,
        reason=f"Amount ${amount:.2f} is within auto-approval threshold ${threshold:.2f}.",
        decision_id=decision_id,
    )


def _approval_mode() -> str:
    return os.getenv("APPROVAL_MODE", "rule").strip().lower()


def _wait_for_interactive_decision(request: ApprovalRequest) -> tuple[ApprovalDecision, str]:
    timeout_seconds = float(os.getenv("APPROVAL_PENDING_TIMEOUT_SECONDS", "180"))
    pending = PendingApproval(
        request=request,
        created_at=datetime.now(UTC).isoformat(),
        event=Event(),
    )

    with PENDING_APPROVALS_LOCK:
        if request.correlation_id in PENDING_APPROVALS:
            raise HTTPException(status_code=409, detail="Correlation ID already pending.")
        PENDING_APPROVALS[request.correlation_id] = pending

    try:
        resolved = pending.event.wait(timeout=timeout_seconds)
        if not resolved or pending.decision is None:
            timeout_decision = ApprovalDecision(
                approved=False,
                reason=f"Approval timed out after {timeout_seconds:.0f} seconds.",
                decision_id=f"timeout_{uuid.uuid4().hex[:12]}",
            )
            return timeout_decision, "interactive-timeout"
        return pending.decision, "interactive-manual"
    finally:
        with PENDING_APPROVALS_LOCK:
            PENDING_APPROVALS.pop(request.correlation_id, None)


def _complete_pending_approval(correlation_id: str, decision: ApprovalDecision) -> bool:
    with PENDING_APPROVALS_LOCK:
        pending = PENDING_APPROVALS.get(correlation_id)
        if pending is None:
            return False
        if pending.decision is not None:
            return True
        pending.decision = decision
        pending.event.set()
        return True


def _build_store() -> TableAuditStore:
    connection_string = os.getenv("AZURE_TABLES_CONNECTION_STRING", "").strip()
    table_endpoint = os.getenv("AZURE_STORAGE_TABLE_ENDPOINT", "").strip()
    table_name = os.getenv("APPROVAL_AUDIT_TABLE_NAME", "ApprovalAudit")

    if connection_string:
        try:
            table_service = TableServiceClient.from_connection_string(conn_str=connection_string)
            return TableAuditStore(table_service=table_service, table_name=table_name)
        except HttpResponseError as ex:
            # Some storage accounts disable shared key auth and require Entra ID.
            if ex.error_code != "KeyBasedAuthenticationNotPermitted" or not table_endpoint:
                raise

            credential = DefaultAzureCredential()
            table_service = TableServiceClient(endpoint=table_endpoint, credential=credential)
            return TableAuditStore(table_service=table_service, table_name=table_name)
    elif table_endpoint:
        credential = DefaultAzureCredential()
        table_service = TableServiceClient(endpoint=table_endpoint, credential=credential)
        return TableAuditStore(table_service=table_service, table_name=table_name)

    raise RuntimeError(
        "Set either AZURE_TABLES_CONNECTION_STRING or AZURE_STORAGE_TABLE_ENDPOINT for persistent audit storage."
    )

STORE = _build_store()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/approve", response_model=ApprovalResponse)
def approve_refund(
    request: ApprovalRequest,
    x_approval_key: str | None = Header(default=None),
) -> ApprovalResponse:
    _validate_api_key(x_approval_key)

    if _approval_mode() == "interactive":
        decision, source = _wait_for_interactive_decision(request)
    else:
        decision = _decide(request)
        source = "rule"

    STORE.save_decision(request=request, decision=decision, source=source)

    return ApprovalResponse(
        approved=decision.approved,
        reason=decision.reason,
        decision_id=decision.decision_id,
    )


@app.post("/manual-decision", response_model=ApprovalResponse)
def create_manual_decision(
    request: ManualDecisionRequest,
    x_approval_key: str | None = Header(default=None),
) -> ApprovalResponse:
    _validate_api_key(x_approval_key)

    decision = ApprovalDecision(
        approved=request.approved,
        reason=request.reason,
        decision_id=f"manual_{uuid.uuid4().hex[:12]}",
    )
    approval_request = ApprovalRequest(
        function_name=request.function_name,
        arguments=request.arguments,
        correlation_id=request.correlation_id,
    )
    resolved_pending = _complete_pending_approval(request.correlation_id, decision)
    source = "interactive-manual" if resolved_pending else "manual"
    STORE.save_decision(request=approval_request, decision=decision, source=source)

    return ApprovalResponse(
        approved=decision.approved,
        reason=decision.reason,
        decision_id=decision.decision_id,
    )


@app.get("/pending")
def list_pending_approvals(limit: int = 50) -> list[dict[str, Any]]:
    safe_limit = min(max(limit, 1), 100)
    with PENDING_APPROVALS_LOCK:
        values = list(PENDING_APPROVALS.values())

    values.sort(key=lambda item: item.created_at, reverse=True)
    items: list[dict[str, Any]] = []
    for pending in values[:safe_limit]:
        items.append(
            {
                "correlation_id": pending.request.correlation_id,
                "function_name": pending.request.function_name,
                "arguments": pending.request.arguments,
                "created_at": pending.created_at,
            }
        )
    return items


@app.post("/pending/{correlation_id}/decision", response_model=ApprovalResponse)
def decide_pending_approval(
    correlation_id: str,
    request: PendingDecisionRequest,
    x_approval_key: str | None = Header(default=None),
) -> ApprovalResponse:
    _validate_api_key(x_approval_key)

    decision = ApprovalDecision(
        approved=request.approved,
        reason=request.reason,
        decision_id=f"manual_{uuid.uuid4().hex[:12]}",
    )

    resolved = _complete_pending_approval(correlation_id, decision)
    if not resolved:
        raise HTTPException(status_code=404, detail="No pending request for the correlation ID.")

    return ApprovalResponse(
        approved=decision.approved,
        reason=decision.reason,
        decision_id=decision.decision_id,
    )


@app.get("/decisions")
def list_decisions(limit: int = 20) -> list[dict[str, Any]]:
    safe_limit = min(max(limit, 1), 100)
    return STORE.list_recent(limit=safe_limit)


@app.get("/", response_class=HTMLResponse)
def approver_ui() -> str:
    return """<!doctype html>
<html>
  <head>
    <meta charset='utf-8' />
    <title>SupportAgent Approver UI</title>
    <style>
      body { font-family: Segoe UI, sans-serif; margin: 2rem; background: #f7fafc; color: #1a202c; }
      .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.25rem; }
      .card { background: white; padding: 1rem; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.07); }
      label { display: block; margin-top: 0.6rem; font-weight: 600; }
      input { width: 100%; padding: 0.55rem; margin-top: 0.25rem; border: 1px solid #d2d6dc; border-radius: 8px; }
      button { margin-top: 1rem; background: #0f766e; color: white; border: none; padding: 0.6rem 0.9rem; border-radius: 8px; cursor: pointer; }
      pre { background: #111827; color: #e5e7eb; padding: 0.8rem; border-radius: 8px; overflow-x: auto; }
    </style>
  </head>
  <body>
    <h1>SupportAgent Approver UI</h1>
    <p>Manual tester for the approval endpoint plus recent audit records from Table Storage.</p>
    <div class='grid'>
      <section class='card'>
        <h2>Pending Requests</h2>
        <p>In interactive mode, approve or deny requests to unblock the waiting agent call.</p>
        <button onclick='loadPending()'>Refresh Pending</button>
        <div id='pendingList'></div>
      </section>
      <section class='card'>
        <h2>Submit Approval Check</h2>
        <label>API Key</label>
        <input id='key' placeholder='Approval API key' />
        <label>Order ID</label>
        <input id='orderId' value='12345' />
        <label>Amount</label>
        <input id='amount' type='number' value='1499' step='0.01' />
        <label>Correlation ID</label>
        <input id='correlation' value='ui-test-1' />
        <button onclick='submitApproval()'>Evaluate Refund</button>
        <label>Manual Reason</label>
        <input id='manualReason' value='Manual reviewer decision' />
        <button onclick='submitManual(true)'>Manual Approve</button>
        <button onclick='submitManual(false)'>Manual Deny</button>
        <h3>Decision</h3>
        <pre id='decision'>No request yet.</pre>
      </section>
      <section class='card'>
        <h2>Recent Decisions</h2>
        <button onclick='loadDecisions()'>Refresh</button>
        <pre id='recent'>No data yet.</pre>
      </section>
    </div>

    <script>
      async function submitApproval() {
        const apiKey = document.getElementById('key').value;
        const payload = {
          function_name: 'issue_refund',
          correlation_id: document.getElementById('correlation').value || 'ui-' + Date.now(),
          arguments: {
            order_id: document.getElementById('orderId').value,
            amount: Number(document.getElementById('amount').value || 0)
          }
        };

        const response = await fetch('/approve', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'x-approval-key': apiKey
          },
          body: JSON.stringify(payload)
        });

        const body = await response.json();
        document.getElementById('decision').textContent = JSON.stringify(body, null, 2);
        await loadDecisions();
      }

      async function submitManual(approved) {
        const apiKey = document.getElementById('key').value;
        const payload = {
          function_name: 'issue_refund',
          correlation_id: document.getElementById('correlation').value || 'ui-' + Date.now(),
          arguments: {
            order_id: document.getElementById('orderId').value,
            amount: Number(document.getElementById('amount').value || 0)
          },
          approved,
          reason: document.getElementById('manualReason').value || (approved ? 'Manually approved' : 'Manually denied')
        };

        const response = await fetch('/manual-decision', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'x-approval-key': apiKey
          },
          body: JSON.stringify(payload)
        });

        const body = await response.json();
        document.getElementById('decision').textContent = JSON.stringify(body, null, 2);
        await loadDecisions();
      }

      async function loadDecisions() {
        const response = await fetch('/decisions?limit=20');
        const body = await response.json();
        document.getElementById('recent').textContent = JSON.stringify(body, null, 2);
      }

      async function decidePending(correlationId, approved) {
        const apiKey = document.getElementById('key').value;
        const reasonInput = document.getElementById('manualReason').value;
        const reason = reasonInput || (approved ? 'Manually approved in UI' : 'Manually denied in UI');

        const response = await fetch(`/pending/${encodeURIComponent(correlationId)}/decision`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'x-approval-key': apiKey
          },
          body: JSON.stringify({ approved, reason })
        });

        const body = await response.json();
        document.getElementById('decision').textContent = JSON.stringify(body, null, 2);
        await loadPending();
        await loadDecisions();
      }

      async function loadPending() {
        const response = await fetch('/pending?limit=50');
        const body = await response.json();
        const pendingList = document.getElementById('pendingList');

        if (!Array.isArray(body) || body.length === 0) {
          pendingList.innerHTML = '<pre>No pending approvals.</pre>';
          return;
        }

        const rows = body.map((item) => {
          const args = JSON.stringify(item.arguments || {}, null, 2);
          const correlationId = item.correlation_id;
          return `
            <div style="border:1px solid #d2d6dc;border-radius:8px;padding:0.7rem;margin-top:0.6rem;">
              <div><strong>Correlation:</strong> ${correlationId}</div>
              <div><strong>Function:</strong> ${item.function_name}</div>
              <div><strong>Created:</strong> ${item.created_at}</div>
              <pre>${args}</pre>
              <button onclick="decidePending('${correlationId}', true)">Approve</button>
              <button onclick="decidePending('${correlationId}', false)">Deny</button>
            </div>
          `;
        });
        pendingList.innerHTML = rows.join('');
      }

      loadDecisions();
      loadPending();
      setInterval(loadPending, 2000);
    </script>
  </body>
</html>
"""


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("APPROVAL_SERVICE_PORT", "8090"))
    uvicorn.run("approval_service:app", host="0.0.0.0", port=port, reload=False)
