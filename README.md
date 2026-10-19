Skatteverket Voice Assistant Edge Function

This Python Edge Function is the integration layer for the Skatteverket English/Swedish Telnyx AI Assistant. The Assistant owns the spoken conversation and workflow. This function handles backend actions during a call:

- limited general tax information in English and Swedish
- Dynamic Webhook responses and session variables
- MCP tools used by the Assistant
- callback and human-transfer records
- per-call state synchronization with a Stateful Actor
- callback and transfer records in native Telnyx KV
- webhook signature validation, idempotency, health checks, and metrics

The function does not provide personalized tax advice.

## Architecture

```text
Caller
  -> Telnyx AI Assistant
      -> Conversation Workflow: language and route selection
      -> Dynamic Webhook -> this Edge Function
      -> MCP tools       -> this Edge Function

This Edge Function
  -> Stateful Actor: one authoritative state owner per call/session
  -> Telnyx KV: callback and human-transfer records
  -> Telnyx Call Control: optional live-transfer action
```

The Actor and KV have different responsibilities:

- The Stateful Actor stores state belonging to one active call: language,
  selected route, callback confirmation, queue status, and lifecycle state.
- KV stores records that must be looked up independently of the active call,
  such as callback requests and transfer tickets.
- The Python function handles request validation, MCP routing, response
  formatting, and metrics.

## Project layout

Keep this layout unchanged when shipping:

```text
function/
  __init__.py       # Exports new() for the Telnyx Python runtime
  func.py           # ASGI-compatible Edge Function implementation
tests/
  test_function.py
  test_integration.py
pyproject.toml
func.toml
```

The deployed runtime expects the package named `function` and an exported
`new` or `handle`. Do not move `func.py` outside the `function/`
directory.

## Prerequisites

- A current `telnyx-edge` CLI
- A deployed Stateful Actor
- A provisioned Telnyx KV namespace
- A secure Telnyx API binding that injects `TELNYX_API_KEY`
- A Telnyx webhook public key if signature validation is enabled
- An MCP bearer token if MCP authentication is enabled

Provision the shared KV namespace once:

```bash
telnyx-edge storage kv create --name skatteverket-voice-state
```

Copy the returned namespace ID. Deploy the Stateful Actor first, then use its
URL as `ACTOR_BASE_URL` in this function.

## Configuration

Copy the example manifest:

```bash
cp func.toml.example func.toml
```

Set the function UUID and name in `[edge_compute]`. Configure these values
in `[env_vars]`:

| Variable | Required | Purpose |
|---|---:|---|
| `REQUIRE_WEBHOOK_SIGNATURE` | Yes | Enables Telnyx webhook verification. Keep `true` for deployment. |
| `TELNYX_WEBHOOK_PUBLIC_KEY_BASE64` | If enabled | Telnyx webhook public key in Base64 form. |
| `STATE_BACKEND` | Yes | Use `actor` for the deployed architecture. |
| `ALLOW_IN_MEMORY_STATE` | Yes | Use `false` in deployment. |
| `ACTOR_BASE_URL` | Yes | URL printed after the Stateful Actor deploys. |
| `KV_NAMESPACE_ID` | Yes | ID returned by KV provisioning. |
| `TELNYX_BASE_URL` | Yes | Normally `https://api.telnyx.com`. |
| `MCP_AUTH_TOKEN` | If enabled | Must match the Assistant MCP server token. |
| `LIVE_QUEUE_NAME` | Yes | Human-transfer record name; default `live_tax_assistance`. |
| `CALLBACK_QUEUE_NAME` | Yes | Callback record name; default `callback_requests`. |
| `CALLBACK_DISPATCH_URL` | No | Optional external callback dispatcher. Leave blank for the demo. |
| `LOG_LEVEL` | No | Usually `INFO`. |

Do not place an API key in `func.toml`. Use the secure Telnyx binding/secret
so the runtime injects `TELNYX_API_KEY`.

## Deploy

Deploy the Stateful Actor first. Then set `ACTOR_BASE_URL` and
`KV_NAMESPACE_ID` in `func.toml` and ship this function:

```bash
telnyx-edge ship --verbose 2>&1 | tee ship.log
```

For a background deployment on Linux:

```bash
nohup telnyx-edge ship --verbose > ship.log 2>&1 & echo $!
```

Check the result:

```bash
telnyx-edge list
telnyx-edge inspect skatt-voice
```

## Assistant portal wiring

Dynamic Webhook URL:

```text
https://YOUR_EDGE_FUNCTION_URL/webhooks/telnyx
```

MCP server URL:

```text
https://YOUR_EDGE_FUNCTION_URL/mcp
```

Configure the same MCP bearer token in the Assistant and the function when
`MCP_AUTH_TOKEN` is enabled.

The Conversation Workflow remains responsible for choosing English or Swedish,
offering information/human/callback routes, collecting and confirming callback
details, and ending or transferring the conversation.

## HTTP endpoints

Health and metrics:

```text
GET /health/live
GET /health/readiness
GET /metrics
```

Workflow actions:

```text
POST /api/information
POST /api/callback
POST /api/transfer
```

Example information request:

```json
{"session_id":"call-123","topic":"deadlines","language":"en-US"}
```

Example callback request:

```json
{"session_id":"call-123","callback_name":"Demo Caller","callback_number":"+46700000000","language":"sv-SE"}
```

Dynamic Webhook:

```text
POST /webhooks/telnyx
POST /webhook
POST /api/workflow
```

When signature validation is enabled, `/webhooks/telnyx` verifies the Telnyx
signature, deduplicates events, updates session state, and returns:

```text
session_id
language
callback_name
callback_number
callback_status
transfer_status
```

## MCP tools

The `/mcp` endpoint exposes:

- `lookup_tax_information`
- `create_callback_request`
- `request_human_transfer`
- `get_call_session`

## Observability

The function emits searchable JSON events, including:

```text
function_configured
function_started
workflow_webhook_processed
workflow_information_started
workflow_callback_received
workflow_callback_queued
workflow_human_transfer_received
workflow_human_transfer_queued
actor_read_completed
actor_write_completed
kv_read_completed
kv_write_completed
kv_write_error
outbound_request_failed
```

View logs and metrics:

```bash
telnyx-edge logs skatt-voice --last 200
curl https://YOUR_EDGE_FUNCTION_URL/metrics
```

Application logs avoid API keys and log only the last four digits of callback
numbers.

## Pre-call testing

Run syntax and local integration tests:

```bash
python -m py_compile function/func.py
python -m pytest -q
```

If pytest does not exit cleanly on Windows, run:

```bash
python tests/test_integration.py
```

The local integration test makes no phone call and spends no telephony credits.
It tests health, webhook variables, bilingual information, callback storage,
human-transfer records, MCP tools, session state, and metrics with an
in-memory store.

For the deployed end-to-end test, use the Actor project's `e2e.test.mjs`:

```bash
export ACTOR_BASE_URL=https://YOUR_ACTOR_FUNCTION_URL
export EDGE_FUNCTION_URL=https://YOUR_EDGE_FUNCTION_URL
export MCP_AUTH_TOKEN=YOUR_MCP_TOKEN
npm test
```

## Troubleshooting

### `ModuleNotFoundError: No module named 'function'`

Check that the wheel contains:

```text
function/__init__.py
function/func.py
```

Verify it locally:

```bash
python -m pip wheel . --no-deps -w dist
python -c "import glob,zipfile; p=glob.glob('dist/*.whl')[0]; print(zipfile.ZipFile(p).namelist())"
```

### Webhook returns `401`

Check the real `TELNYX_WEBHOOK_PUBLIC_KEY_BASE64). For temporary local
testing only, set `REQUIRE_WEBHOOK_SIGNATURE=false`.

### Actor state is unavailable

```bash
curl https://YOUR_ACTOR_FUNCTION_URL/health/liveness
curl https://YOUR_ACTOR_FUNCTION_URL/sessions/test-123/state
```

### MCP returns `401`

The MCP token in the Assistant must exactly match `MCP_AUTH_TOKEN`.

### Deployment fails

```bash
telnyx-edge ship status skatt-voice --logs
```

Wait for an operation to finish before resetting or shipping again.

