# ApprovalService

## Local auth setup

The service supports two local authentication modes for Azure Table Storage.

### Option 1: Connection string (shared key)
Use this only when shared key auth is allowed on the storage account.

1. Set these values in `.env`:
   - `AZURE_TABLES_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=<account>;AccountKey=<key>;EndpointSuffix=core.windows.net`
   - `APPROVAL_AUDIT_TABLE_NAME=ApprovalAudit`
2. Start the service:
   - `python.exe .\approval_service.py`

### Option 2: Endpoint + Entra ID (recommended)
Use this when key auth is disabled, or when you prefer user identity auth.

1. Set these values in `.env`:
   - `AZURE_STORAGE_TABLE_ENDPOINT=https://<account>.table.core.windows.net`
   - `APPROVAL_AUDIT_TABLE_NAME=ApprovalAudit`
   - Optional: leave `AZURE_TABLES_CONNECTION_STRING` empty.
2. Sign in locally:
   - `az login`
3. Ensure your signed-in identity has a table data role on the storage account (for example, Storage Table Data Contributor).
4. Start the service:
   - `python.exe .\approval_service.py`

## Notes

- If both values are set, the service tries connection string first.
- If key auth is blocked with `KeyBasedAuthenticationNotPermitted`, the service automatically falls back to endpoint + Entra ID.

## Interactive approval mode

You can run the service in interactive mode so `/approve` waits for a human decision from the UI.

1. Set these values in `.env`:
   - `APPROVAL_MODE=interactive`
   - Optional: `APPROVAL_PENDING_TIMEOUT_SECONDS=180`
   - Optional auth key: `APPROVAL_SERVICE_API_KEY=<shared-key>`
2. Start the service:
   - `python.exe .\approval_service.py`
3. Open `http://localhost:8090` and use the **Pending Requests** card to approve or deny.

### How interactive flow works

- Agent harness calls `POST /approve`.
- Service enqueues the request and blocks until a reviewer responds or timeout is reached.
- Reviewer approves/denies from the UI, which calls `POST /pending/{correlation_id}/decision`.
- The waiting `/approve` call returns that decision back to the harness.

### Interactive endpoints

- `GET /pending` - list queued approval requests.
- `POST /pending/{correlation_id}/decision` - approve/deny one pending request.
