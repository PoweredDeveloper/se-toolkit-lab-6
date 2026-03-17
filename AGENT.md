## Agent Overview

This project includes a simple CLI agent implemented in `agent.py`.  
The agent takes a question as a command-line argument, sends it to an LLM that
supports the OpenAI-compatible Chat Completions API, and prints a structured
JSON response to `stdout`.

The agent is intentionally minimal in Task&nbsp;1: no tools, no multi-turn
conversation, and no domain-specific logic. Those will be added in later tasks.

## LLM Provider and Model

- **Provider**: Qwen Code API (recommended) or any OpenAI-compatible endpoint.
- **Model**: Controlled via the `LLM_MODEL` environment variable.
  - Example: `qwen3-coder-plus`.
- **Endpoint base URL**: `LLM_API_BASE`, for example:
  - `http://<vm-ip>:42005/v1` when using the Qwen Code API proxy.

The agent does not hardcode any provider-specific values. All configuration is
read from environment variables, which are usually loaded from
`.env.agent.secret`.

## Configuration

Create the secret configuration file:

```bash
cp .env.agent.example .env.agent.secret
```

Then edit `.env.agent.secret` and set:

- `LLM_API_BASE` — Base URL for the OpenAI-compatible API (without a trailing slash or with `/v1`).
- `LLM_API_KEY` — API key for your LLM provider.
- `LLM_MODEL` — Model name to use (for example `qwen3-coder-plus`).

At startup, `agent.py` parses `.env.agent.secret` as a simple `KEY=VALUE` file
and populates missing values in `os.environ`. Existing environment variables are
not overwritten, so you can also inject configuration through your shell or
process manager.

## CLI Interface

Run the agent with `uv`:

```bash
uv run agent.py "What does REST stand for?"
```

- **Input**: The first positional argument is the user question (required).
- **Output**: One line of JSON printed to `stdout`:

```json
{"answer": "Representational State Transfer.", "tool_calls": []}
```

Rules:

- `answer` (string) and `tool_calls` (array) are always present.
- For Task&nbsp;1, `tool_calls` is always an empty list.
- Only the JSON line is written to `stdout`; all diagnostics go to `stderr`.
- On success, the process exits with code `0`.

If the question argument is missing, the agent prints a usage message to
`stderr` and exits with status code `1`.

## Request/Response Flow

1. Parse the CLI argument into a question string.
2. Load `LLM_API_BASE`, `LLM_API_KEY`, and `LLM_MODEL` from the environment
   (optionally via `.env.agent.secret`).
3. Build a minimal system prompt:
   - Answer concisely.
   - Use plain text.
   - Tools are disabled.
4. Send a `POST` request to `${LLM_API_BASE}/chat/completions` with:
   - `model`: value from `LLM_MODEL`.
   - `messages`: one system message and one user message.
5. Parse the JSON response and extract:
   - `choices[0].message.content` as the answer text.
6. Print the final JSON object:
   - `{"answer": <string>, "tool_calls": []}`.

### Error Handling

- **Configuration errors** (missing `LLM_API_BASE`, `LLM_API_KEY`, or `LLM_MODEL`):
  - A clear message is printed to `stderr`.
  - The process exits with a non-zero status code.
- **Network/HTTP/JSON errors** when calling the LLM:
  - Details are printed to `stderr`.
  - A structured JSON error is printed to `stdout`:

    ```json
    {"answer": "", "tool_calls": [], "error": "<short description>"}
    ```

  - The process exits with a non-zero status code.

## Tests

A regression test is defined in `backend/tests/unit/test_agent_cli.py`. It:

- Runs `agent.py` as a subprocess with a sample question.
- Asserts that the process exits with status code `0`.
- Parses `stdout` as JSON.
- Verifies that:
  - `answer` exists and is a string.
  - `tool_calls` exists and is a list.

This guards the basic contract expected by the lab evaluation runner and future
tasks that build on this agent.

