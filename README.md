# LLM Shadow Proxy

`llm-shadow` is a small FastAPI service that sits in front of two OpenAI-compatible chat-completions backends:

- a `baseline` model that serves the user-facing response
- a `candidate` model that receives the same request in the background for comparison

The proxy returns the baseline response immediately, then logs both baseline and candidate outcomes to a local JSONL file for offline analysis.

## What v1 Does

- Exposes `POST /v1/chat/completions`
- Accepts non-streaming OpenAI-compatible chat-completions requests
- Forwards the request to the baseline upstream first
- Returns the baseline response to the caller
- Sends the same request to the candidate upstream in a background task
- Logs one `baseline` record and one `candidate` record per successful baseline request
- Stores both the original request payload and the raw upstream response payload in each record
- Includes a CLI for basic offline summaries like tool-match percentage and average latency

## What v1 Does Not Do

- Streaming responses
- Retries or fallback routing
- Provider-specific adapters
- Persistent background job processing
- Built-in semantic LLM judging beyond a stub hook

## Project Layout

```text
.
├── config/
├── eval/
├── logger/
├── normalizer/
├── proxy/
├── tests/
└── utils/
```

Key files:

- `proxy/main.py`: FastAPI app and shared client lifecycle
- `proxy/handlers.py`: request handling and background shadow flow
- `proxy/client.py`: async OpenAI-compatible upstream client
- `logger/schema.py`: JSONL record shape
- `normalizer/normalize.py`: text + tool-call extraction
- `eval/cli.py`: offline metrics CLI

## Requirements

- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv)

## Quick Start With Docker

Build the image locally:

```bash
docker build -t llm-shadow:local .
```

Run the proxy with your `.env` file and a mounted logs directory:

```bash
mkdir -p logs
docker run --rm \
  --env-file .env \
  -p 8000:8000 \
  -v "$(pwd)/logs:/app/logs" \
  llm-shadow:local
```

If you publish the image to GHCR, users can run:

```bash
docker run --rm \
  --env-file .env \
  -p 8000:8000 \
  -v "$(pwd)/logs:/app/logs" \
  ghcr.io/<owner>/llm-shadow:latest
```

The container registry only stores the image. It does not store runtime logs.

To keep logs after the container exits, mount a host directory or Docker volume. With the default `LOG_FILE=logs/logs.jsonl`, the app writes to `/app/logs/logs.jsonl` inside the container, and the bind mount above maps that file back to `./logs/logs.jsonl` on your machine.

After the container handles requests, inspect the host-side log file directly:

```bash
cat logs/logs.jsonl
uv run python -m eval.cli --file logs/logs.jsonl
```

If you do not mount a directory or volume, the logs stay inside the container filesystem and are lost when the container is removed.

## Setup From Source

Install dependencies:

```bash
uv sync --extra dev
```

If you also want DuckDB locally for analysis:

```bash
uv sync --extra dev --extra analysis
```

## Configuration

The app reads configuration from environment variables.

Required:

- `BASELINE_URL`: base URL for the baseline upstream, for example `https://api.openai.com`
- `CANDIDATE_URL`: base URL for the candidate upstream
- `BASELINE_MODEL`: model name sent to the baseline upstream if the incoming payload does not include `model`
- `CANDIDATE_MODEL`: model name sent to the candidate upstream if the incoming payload does not include `model`

Authentication, choose one per upstream:

- `BASELINE_API_KEY`: converted to `Authorization: Bearer ...`
- `BASELINE_AUTH_HEADER`: full override for the `Authorization` header
- `CANDIDATE_API_KEY`
- `CANDIDATE_AUTH_HEADER`

Optional:

- `TIMEOUT`: upstream request timeout in seconds. Default: `30`
- `LOG_FILE`: JSONL output path. Default: `logs/logs.jsonl`

Example:

```bash
export BASELINE_URL="https://api.openai.com"
export CANDIDATE_URL="https://my-candidate-proxy.example.com"
export BASELINE_MODEL="gpt-4o-mini"
export CANDIDATE_MODEL="candidate-model"
export BASELINE_API_KEY="sk-..."
export CANDIDATE_API_KEY="sk-..."
export LOG_FILE="logs/logs.jsonl"
```

## Running The Proxy

Source users can start the service with the packaged console command:

```bash
uv run llm-shadow-serve
```

The developer path is still available:

```bash
uv run uvicorn proxy.main:app --host 0.0.0.0 --port 8000 --reload
```

Container users do not need either command above because the image starts the service automatically.

The endpoint is:

```text
POST /v1/chat/completions
```

Example request:

```bash
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What is the weather in SF?"}
    ]
  }'
```

If the server is running in Docker, use the same `curl` command against `http://127.0.0.1:8000`.

## Request Flow

For each incoming request:

1. The proxy generates a `trace_id`.
2. The baseline upstream is called synchronously.
3. If baseline succeeds, that response is returned immediately to the caller.
4. A background task sends the same request payload to the candidate upstream.
5. The proxy normalizes both responses.
6. Two JSONL records are appended: one for `baseline`, one for `candidate`.

If the baseline request fails:

- the error is passed through to the caller
- the candidate request is not started
- no paired shadow records are written

If the candidate request fails:

- the caller still receives the baseline response
- the candidate record is still written with `status="error"`

## Log Format

Each line in `LOG_FILE` is one JSON object. Records include:

- `trace_id`
- `timestamp`
- `type`: `baseline` or `candidate`
- `model`
- `text`
- `tool_name`
- `tool_args`
- `latency_ms`
- `status`
- `error_type`
- `error_message`
- `raw_request`
- `raw_response`

Normalization behavior:

- `text` comes from `choices[0].message.content`
- `tool_name` and `tool_args` come from the first tool call only
- invalid tool-call argument JSON is stored as the raw string
- missing fields are stored as `null`

Example record:

```json
{
  "trace_id": "8d1c6b8f6a8d4a8ca0f6030a3196f110",
  "timestamp": "2026-04-01T18:22:31.123456+00:00",
  "type": "baseline",
  "model": "gpt-4o-mini",
  "text": "The weather in San Francisco is often cool and foggy.",
  "tool_name": null,
  "tool_args": null,
  "latency_ms": 412,
  "status": "ok",
  "error_type": null,
  "error_message": null,
  "raw_request": {
    "messages": [
      {
        "role": "user",
        "content": "What is the weather in SF?"
      }
    ]
  },
  "raw_response": {
    "choices": [
      {
        "message": {
          "content": "The weather in San Francisco is often cool and foggy."
        }
      }
    ]
  }
}
```

## Running Tests

Run the test suite with:

```bash
uv run python -m pytest
```

Validate the Docker image locally with:

```bash
docker build -t llm-shadow:test .
```

The current tests cover:

- normalization behavior
- log record creation and JSONL writes
- proxy integration flow
- baseline failure pass-through
- candidate error logging
- CLI summary behavior

## Offline Evaluation

Summarize a log file with:

```bash
uv run python -m eval.cli --file logs/logs.jsonl
```

Current CLI output includes:

- total record count
- trace count
- paired trace count
- successful pair count
- tool-comparable pair count
- tool-match percentage
- average baseline latency
- average candidate latency

## DuckDB Example

If you installed the `analysis` extra, you can inspect the logs with DuckDB:

```bash
uv run python -c "import duckdb; print(duckdb.read_json('logs/logs.jsonl').limit(5).df())"
```

## Development Notes

- The baseline and candidate upstreams are expected to be OpenAI-compatible.
- The incoming payload is forwarded as-is, except the client fills in `model` if it is missing.
- Runtime configuration is environment-variable only.
- The container image is intended to be stateless apart from the mounted log directory.
- GitHub Actions runs tests on pushes and PRs, and publishes tagged images to GHCR.
- Background shadowing is in-process and best-effort for v1.
- File logging is simple append-only JSONL by design for this first version.
