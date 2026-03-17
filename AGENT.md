## Agent Overview

This project includes a simple CLI agent implemented in `agent.py`.  
The agent takes a question as a command-line argument, sends it to an LLM that
supports the OpenAI-compatible Chat Completions API **with tool/function calling**,
and prints a structured JSON response to `stdout`.

In Task&nbsp;2, the agent becomes a **documentation agent**: it can call tools to
inspect the repository wiki (`wiki/`) and cite the source section used.

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
{"answer": "Representational State Transfer.", "source": "wiki/rest-api.md#rest", "tool_calls": []}
```

Rules:

- `answer` (string), `source` (string), and `tool_calls` (array) are always present.
- `tool_calls` is populated when the agent used tools during the run.
- Only the JSON line is written to `stdout`; all diagnostics go to `stderr`.
- On success, the process exits with code `0`.

If the question argument is missing, the agent prints a usage message to
`stderr` and exits with status code `1`.

## Request/Response Flow

1. Parse the CLI argument into a question string.
2. Load `LLM_API_BASE`, `LLM_API_KEY`, and `LLM_MODEL` from the environment
   (optionally via `.env.agent.secret`).
3. Build a system prompt strategy:
   - Use `list_files` to discover relevant wiki files.
   - Use `read_file` to read markdown content.
   - Provide a final answer **and** a `source` reference (`wiki/<file>.md#<anchor>`).
   - Return the final response as a JSON object in the assistant message content.
4. Send a `POST` request to `${LLM_API_BASE}/chat/completions` with tool schemas:
   - `model`: value from `LLM_MODEL`.
   - `messages`: system + user + (tool results as needed).
   - `tools`: definitions for `list_files` and `read_file`.
5. Enter an agentic loop (max **10 tool calls** total):
   - If the model returns `tool_calls`, execute them and send results back as `tool` messages.
   - If the model returns final text (no `tool_calls`), parse it as JSON and extract `answer` and `source`.
6. Print the final JSON object:
   - `{"answer": <string>, "source": <string>, "tool_calls": [...]}`.

## Tools

The agent exposes two tools to the LLM:

- **`list_files`**
  - **Args**: `{"path": "<relative-dir>"}` (example: `{"path":"wiki"}`)
  - **Result**: newline-separated directory entries (or an error string)
- **`read_file`**
  - **Args**: `{"path": "<relative-file>"}` (example: `{"path":"wiki/git.md"}`)
  - **Result**: UTF-8 file contents (or an error string)

### Tool security

Both tools reject:

- Absolute paths
- Any path containing `..`
- Any resolved path outside the project root directory

### Error Handling

- **Configuration errors** (missing `LLM_API_BASE`, `LLM_API_KEY`, or `LLM_MODEL`):
  - A clear message is printed to `stderr`.
  - The process exits with a non-zero status code.
- **Network/HTTP/JSON errors** when calling the LLM:
  - Details are printed to `stderr`.
  - A structured JSON error is printed to `stdout`:

    ```json
    {"answer": "", "source": "", "tool_calls": [], "error": "<short description>"}
    ```

  - The process exits with a non-zero status code.

## Tests

A regression test is defined in `backend/tests/unit/test_agent_cli.py`. It:

- Runs `agent.py` as a subprocess with a sample question.
- Asserts that the process exits with status code `0`.
- Parses `stdout` as JSON.
- Verifies that:
  - `answer` exists and is a string.
  - `source` exists and is a string.
  - `tool_calls` exists and is a list.

This guards the basic contract expected by the lab evaluation runner and future
tasks that build on this agent.

Additional Task&nbsp;2 regression tests run `agent.py` against a local stub LLM
server to verify the tool-calling loop populates `tool_calls` and produces a
wiki `source` reference.

