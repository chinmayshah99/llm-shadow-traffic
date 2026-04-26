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
- Includes offline tooling for basic summaries and config-driven judge runs

## What v1 Does Not Do

- Streaming responses
- Retries or fallback routing
- Provider-specific adapters
- Persistent background job processing
- Built-in provider-backed semantic judging out of the box

## Project Layout

```text
. 
├── config/
├── examples/
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
- `LOG_BACKUP_METHOD`: backup backend for completed log segments. Default: `none`. Supported: `none`, `s3`
- `LOG_ROTATE_MAX_BYTES`: rotate the active JSONL file after this many bytes. Default: `26214400` (25 MB)
- `S3_BACKUP_BUCKET`: required when `LOG_BACKUP_METHOD=s3`
- `S3_BACKUP_PREFIX`: optional object prefix for uploaded segments
- `AWS_REGION`: optional AWS region override for the S3 client
- `S3_BACKUP_KMS_KEY_ID`: optional KMS key for server-side encryption
- `S3_BACKUP_STORAGE_CLASS`: optional S3 storage class for uploaded segments

Example:

```bash
export BASELINE_URL="https://api.openai.com"
export CANDIDATE_URL="https://my-candidate-proxy.example.com"
export BASELINE_MODEL="gpt-4o-mini"
export CANDIDATE_MODEL="candidate-model"
export BASELINE_API_KEY="sk-..."
export CANDIDATE_API_KEY="sk-..."
export LOG_FILE="logs/logs.jsonl"
export LOG_BACKUP_METHOD="s3"
export LOG_ROTATE_MAX_BYTES="26214400"
export S3_BACKUP_BUCKET="my-shadow-backups"
export S3_BACKUP_PREFIX="prod/llm-shadow"
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
7. When the active log file reaches `LOG_ROTATE_MAX_BYTES`, it is rotated into a timestamped JSONL segment.
8. The completed segment is handed to the configured backup backend. For S3, the upload is best-effort and does not block local logging.

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
- `tool_calls`
- `latency_ms`
- `status`
- `error_type`

## Log Rotation And Backup

The proxy writes to `LOG_FILE` locally first. Local disk remains the source of truth.

When the active file reaches `LOG_ROTATE_MAX_BYTES`, the logger:

- renames the active file to `logs.<timestamp>.<sequence>.jsonl`
- creates a fresh empty `LOG_FILE`
- sends the completed segment to the configured backup sink

With `LOG_BACKUP_METHOD=s3`, each rotated segment is uploaded to:

- `<prefix>/logs.<timestamp>.<sequence>.jsonl` when `S3_BACKUP_PREFIX` is set
- `logs.<timestamp>.<sequence>.jsonl` when no prefix is set

If an S3 upload fails, the rotated local segment is kept on disk and request handling continues normally. The current implementation does not retry uploads in the request path.
- `error_message`
- `raw_request`
- `raw_response`

Normalization behavior:

- `text` comes from `choices[0].message.content`
- `tool_calls` stores all tool calls in order as `{name, arguments}`
- `tool_name` and `tool_args` still come from the first tool call for backward compatibility
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
  "tool_calls": [],
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
uv run python -m eval.cli summary --file logs/logs.jsonl
```

The old form still works for backward compatibility:

```bash
uv run python -m eval.cli --file logs/logs.jsonl
```

Generate a static HTML report with:

```bash
uv run --extra analysis python -m eval.report --file logs/logs.jsonl --out logs/report.html
```

Or use the packaged console script:

```bash
uv run --extra analysis llm-shadow-report --file logs/logs.jsonl --out logs/report.html
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

The HTML report adds:

- average, p50, and p95 latency for baseline and candidate
- candidate error counts and status breakdowns
- top tools, mismatched tool calls, recent trace samples, and worst latency deltas
- an optional batch-results section when you pass `--batch-file`

Example with a batch JSONL file:

```bash
uv run --extra analysis python -m eval.report \
  --file logs/logs.jsonl \
  --batch-file logs/batch-output.jsonl \
  --out logs/report.html
```

The report is written to the explicit `--out` path you provide.

## Judge Examples

Run judges against a log file with:

```bash
uv run python -m eval.cli judge --file logs/logs.jsonl --config path/to/judges.json
```

If you want the built-in demo semantic backend, add:

```bash
uv run python -m eval.cli judge \
  --file logs/logs.jsonl \
  --config path/to/judges.json \
  --semantic-backend token-overlap
```

Judge configs are JSON objects with a top-level `judges` list.

### 1. Tool Call Match

Use this when baseline and candidate should produce the same ordered tool-call sequence.

```json
{
  "judges": [
    {
      "name": "weather-tool-match",
      "type": "tool_call_match"
    }
  ]
}
```

### 2. Regex Match

Use this when the output text must contain a value in a known format.

```json
{
  "judges": [
    {
      "name": "ticket-id-regex",
      "type": "regex_match",
      "field": "text",
      "pattern": "TICKET-[0-9]{6}"
    }
  ]
}
```

### 3. LLM Judge For Similar Text Or Same Semantic Meaning

Use this when exact wording does not matter, but the meaning should stay the same. In v1, semantic scoring is pluggable. The default backend returns no score, and the demo `token-overlap` backend provides a lightweight local approximation.

```json
{
  "judges": [
    {
      "name": "answer-semantic-match",
      "type": "semantic_match",
      "field": "text",
      "threshold": 0.5,
      "rubric": "Pass when the candidate answer has the same meaning as the baseline answer, even if wording, order, or style differ."
    }
  ]
}
```

### 4. Tool Call Match With Variables

Use this when the tool must match and some arguments should be checked structurally instead of by exact literal value.

```json
{
  "judges": [
    {
      "name": "search-tool-with-variables",
      "type": "tool_call_match",
      "tool_calls": [
        {
          "name": "search_docs",
          "arguments": {
            "query": {
              "var": "$query",
              "match": "exact"
            },
            "top_k": {
              "var": "$top_k",
              "match": "exact"
            }
          }
        }
      ]
    }
  ]
}
```

### 5. Tool Call Match With Variables, And Semantic Match For String Values

Use this when the tool and argument shape must match, but string arguments can be paraphrased as long as they mean the same thing.

```json
{
  "judges": [
    {
      "name": "search-tool-semantic-args",
      "type": "tool_call_match",
      "tool_calls": [
        {
          "name": "search_docs",
          "arguments": {
            "query": {
              "var": "$query",
              "match": "semantic",
              "threshold": 0.3,
              "rubric": "Pass when the search intent is the same."
            },
            "top_k": {
              "var": "$top_k",
              "match": "exact"
            },
            "filters": {
              "var": "$filters",
              "match": "exact"
            }
          }
        }
      ]
    }
  ]
}
```

Example semantic argument match:

- baseline tool args: `{"query": "best way to rotate API keys safely", "top_k": 5}`
- candidate tool args: `{"query": "safe way to rotate API keys", "top_k": 5}`

This should pass because the tool is the same, `top_k` matches exactly, and the two `query` strings are semantically equivalent.

## Example Scripts

The repository includes runnable examples under `examples/`:

```bash
python examples/tool_call_match_example.py
python examples/regex_match_example.py
python examples/semantic_match_example.py
python examples/tool_call_variables_example.py
python examples/tool_call_semantic_args_example.py
```

Each script builds a tiny sample dataset, writes a JSON judge config, runs the framework, and prints pass/fail output with match details.

## Judge Config Reference

Supported judge types:

- `tool_call_match`
- `regex_match`
- `semantic_match`

Common judge fields:

- `name`: stable label for reporting
- `type`: judge type

`regex_match` fields:

- `field`: dotted path such as `text` or `tool_calls.0.arguments.query`
- `pattern`: Python regex

`semantic_match` fields:

- `field`: dotted path to compare between baseline and candidate
- `threshold`: minimum semantic score
- `rubric`: optional text passed to the semantic backend

`tool_call_match` fields:

- omit `tool_calls` to require exact equality for the full ordered tool-call sequence
- `tool_calls`: ordered list of call specs to validate
- each call spec can include `name`
- each call spec can include nested `arguments`

Variable specs inside `arguments`:

- `{"var": "$query", "match": "exact"}`
- `{"var": "$query", "match": "regex"}`
- `{"var": "$query", "match": "semantic", "threshold": 0.3, "rubric": "..."}`

When a variable is first seen, the framework binds the baseline value. Later uses of the same variable must match that same baseline value, and the candidate value is checked using the configured match mode.

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
- File logging is local-first JSONL with size-based segment rotation and optional best-effort S3 backups.
