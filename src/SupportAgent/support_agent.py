# support_agent.py — Agent Harness demo (Microsoft Agent Framework, GA)
import os
import logging
import time
import uuid
from typing import Annotated, Any

import httpx
from azure.identity import DefaultAzureCredential
from agent_framework import (
    Agent,
    FunctionInvocationContext,
    function_middleware,
)
from agent_framework.openai import OpenAIChatCompletionClient
from agent_framework_foundry_hosting import ResponsesHostServer
from pydantic import Field

from dotenv import load_dotenv; 
load_dotenv()


logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Silence verbose Azure Monitor exporter logs in console output.
_azure_monitor_logger = logging.getLogger("azure.monitor.opentelemetry.exporter.export._base")
_azure_monitor_logger.setLevel(logging.ERROR)
_azure_monitor_logger.propagate = False


def _as_dict(arguments: Any) -> dict[str, Any]:
    if isinstance(arguments, dict):
        return arguments
    if hasattr(arguments, "items"):
        return dict(arguments.items())
    return {}


async def _request_refund_approval(function_name: str, arguments: dict[str, Any]) -> tuple[bool, str, str, str]:
    service_url = os.getenv("APPROVAL_SERVICE_URL", "").strip()
    if not service_url:
        service_url = "http://localhost:8090"
        logger.warning("APPROVAL_SERVICE_URL not set. Falling back to %s", service_url)

    timeout_seconds = float(os.getenv("APPROVAL_TIMEOUT_SECONDS", "240"))
    correlation_id = f"approval_{uuid.uuid4().hex[:16]}"
    headers = {"Content-Type": "application/json"}

    api_key = os.getenv("APPROVAL_SERVICE_API_KEY", "").strip()
    if api_key:
        headers["x-approval-key"] = api_key

    payload = {
        "function_name": function_name,
        "arguments": arguments,
        "correlation_id": correlation_id,
    }

    endpoint = f"{service_url.rstrip('/')}/approve"
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.post(endpoint, json=payload, headers=headers)
        response.raise_for_status()
        body = response.json()

    approved = bool(body.get("approved", False))
    reason = str(body.get("reason", "No decision reason provided."))
    decision_id = str(body.get("decision_id", ""))
    return approved, reason, decision_id, correlation_id

# Auxiliary functions
def _apply_streaming_function_name_workaround() -> None:
    """Patch known hosting bug where streamed function calls may have empty names."""
    try:
        from agent_framework_foundry_hosting import _responses as responses_module
    except Exception:
        return

    tracker_cls = getattr(responses_module, "_OutputItemTracker", None)
    if tracker_cls is None:
        return

    original = getattr(tracker_cls, "_open_function_call", None)
    if original is None or getattr(tracker_cls, "_name_patch_applied", False):
        return

    def _patched_open_function_call(self, content):
        # Fallbacks avoid ValueError("name must be a non-empty string") in stream builder.
        safe_name = (getattr(content, "name", None) or "unknown_tool_call").strip() or "unknown_tool_call"
        safe_call_id = getattr(content, "call_id", None) or f"call_{uuid.uuid4().hex}"

        self._fc_builder = self._stream.add_output_item_function_call(
            name=safe_name,
            call_id=safe_call_id,
        )
        self._active_type = "function_call"
        self._active_id = safe_call_id
        yield self._fc_builder.emit_added()

    tracker_cls._open_function_call = _patched_open_function_call
    tracker_cls._name_patch_applied = True

# ---------------------------------------------------------------------------
# 1. SKILLS  (plain Python functions = tools the agent can call)
# ---------------------------------------------------------------------------
# A tiny fake "database" so the demo is self-contained — no external calls.
_ORDERS = {
    "12345": {"item": "Surface Laptop 7", "total": 1499.00, "status": "delivered"},
    "67890": {"item": "Xbox Series X",     "total":  499.00, "status": "shipped"},
}

def lookup_order(
    order_id: Annotated[str, Field(description="The customer's order ID.")],
) -> str:
    """Look up an order's item, total, and status by order ID."""
    o = _ORDERS.get(order_id)
    if not o:
        return f"No order found with ID {order_id}."
    return f"Order {order_id}: {o['item']}, ${o['total']:.2f}, status: {o['status']}."

def issue_refund(
    order_id: Annotated[str, Field(description="The order ID to refund.")],
    amount: Annotated[float, Field(description="The amount to refund in USD.")],
) -> str:
    """Issue a refund for an order. SENSITIVE — guarded by the approval gate."""
    return f"✅ Refund of ${amount:.2f} issued for order {order_id}."

# ---------------------------------------------------------------------------
# 2. MIDDLEWARE  (the harness "control layer" — wraps tool calls)
# ---------------------------------------------------------------------------
# Function middleware fires on every tool invocation. It can inspect args,
# log, block, or override the result — without touching the skill code.

@function_middleware
async def timing_logger(context: FunctionInvocationContext, next) -> None:
    """Logs every tool call and how long it took."""
    name = context.function.name
    logger.info("[harness] calling tool: %s", name)
    start = time.time()
    await next()
    logger.info("[harness] %s finished in %.2fs", name, time.time() - start)

@function_middleware
async def approval_gate(context: FunctionInvocationContext, next) -> None:
    """External approval check before any refund executes."""
    if context.function.name == "issue_refund":
        args = _as_dict(context.arguments)
        logger.warning("[APPROVAL REQUIRED] issue_refund(%s)", args)

        try:
            approved, reason, decision_id, correlation_id = await _request_refund_approval(
                function_name=context.function.name,
                arguments=args,
            )
        except Exception as ex:
            fail_mode = os.getenv("APPROVAL_FAIL_MODE", "deny").strip().lower()
            logger.exception("Approval service call failed: %s", ex)
            if fail_mode == "allow":
                logger.warning("Approval fallback mode is allow. Continuing without approval.")
                await next()
                return
            context.result = (
                "❌ Refund denied because approval service call failed "
                f"({type(ex).__name__}: {ex})."
            )
            return

        if not approved:
            context.result = f"❌ Refund denied by approval service. Reason: {reason}"
            logger.info(
                "Refund denied. decision_id=%s correlation_id=%s reason=%s",
                decision_id,
                correlation_id,
                reason,
            )
            return

        logger.info(
            "Refund approved. decision_id=%s correlation_id=%s reason=%s",
            decision_id,
            correlation_id,
            reason,
        )
    await next()

# ---------------------------------------------------------------------------
# 3. THE AGENT  (harness assembles skills + middleware around the model)
# ---------------------------------------------------------------------------
def build_agent() -> Agent:
    # OpenAIChatClient supports Azure OpenAI when azure_endpoint/api_version are set.
    # These values are read from env / .env for local runs.
    model = (
        os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
        or os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME")
    )
    if not model:
        raise ValueError(
            "Missing AZURE_OPENAI_CHAT_DEPLOYMENT_NAME (or AZURE_AI_MODEL_DEPLOYMENT_NAME)."
        )

    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    credential = None if api_key else DefaultAzureCredential()

    # Use Chat Completions client so OPENAI_API_VERSION=2024-06-01 remains supported.
    client = OpenAIChatCompletionClient(
        model=model,
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version=os.getenv("OPENAI_API_VERSION"),
        api_key=api_key,
        credential=credential,
    )
    return Agent(
        client=client,
        name="SupportAgent",
        instructions=(
            "You are a customer support agent. Use lookup_order to find orders "
            "and issue_refund to refund them. Confirm details before refunding."
        ),
        tools=[lookup_order, issue_refund],
        middleware=[timing_logger, approval_gate],
        # History will be managed by the hosting infrastructure, thus there
        # is no need to store history by the service. Learn more at:
        # https://developers.openai.com/api/reference/resources/responses/methods/create
        default_options={"store": False}
    )

# ---------------------------------------------------------------------------
# 4. RUN  (memory via a thread keeps context across turns)
# ---------------------------------------------------------------------------
def main() -> None:
    _apply_streaming_function_name_workaround()
    agent = build_agent()
    # session = agent.create_session()   # <-- this is the agent's memory

    # # Turn 1: a plain skill call (your "baseline" moment)
    # r1 = await agent.run("Look up order 12345.", session=session)
    # print(f"\nAgent: {r1.text}\n")

    # # Turn 2: "refund it" — only works because memory recalls order 12345.
    # # This also trips the approval gate before the refund runs.
    # r2 = await agent.run("Refund it in full.", session=session)
    # print(f"\nAgent: {r2.text}\n")

    server = ResponsesHostServer(agent)
    server.run()

if __name__ == "__main__":
    main()
