import json
import os
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class _StubChatHandler(BaseHTTPRequestHandler):
    # Set by the test when the server is created.
    responses = []
    call_index = 0

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        # Keep test output clean.
        return

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/chat/completions":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", "0"))
        _ = self.rfile.read(length) if length else b""

        idx = type(self).call_index
        type(self).call_index += 1

        payload = type(self).responses[min(idx, len(type(self).responses) - 1)]
        body = json.dumps(payload).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _run_stub_server(responses):
    port = _free_port()
    handler = _StubChatHandler
    handler.responses = responses
    handler.call_index = 0
    server = HTTPServer(("127.0.0.1", port), handler)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def _run_agent(question: str, api_base: str) -> dict:
    project_root = Path(__file__).resolve().parent.parent
    agent_path = project_root / "agent.py"
    env = os.environ.copy()
    env.update(
        {
            "LLM_API_BASE": api_base,
            "LLM_API_KEY": "test",
            "LLM_MODEL": "test-model",
        }
    )

    result = subprocess.run(
        [sys.executable, str(agent_path), question],
        cwd=project_root,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, f"agent.py exited with {result.returncode}: {result.stderr}"
    return json.loads(result.stdout.strip())


def test_documentation_agent_uses_read_file_for_merge_conflict() -> None:
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "list_files", "arguments": json.dumps({"path": "wiki"})},
                            }
                        ],
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": "call_2",
                                "type": "function",
                                "function": {
                                    "name": "read_file",
                                    "arguments": json.dumps({"path": "wiki/git.md"}),
                                },
                            }
                        ],
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "answer": "A merge conflict happens when Git can't automatically combine changes. "
                                "Remove conflict markers, choose or combine changes, then commit.",
                                "source": "wiki/git.md#merge-conflict",
                            }
                        ),
                    }
                }
            ]
        },
    ]

    server, port = _run_stub_server(responses)
    try:
        data = _run_agent("How do you resolve a merge conflict?", f"http://127.0.0.1:{port}/v1")
    finally:
        server.shutdown()

    assert data["source"] == "wiki/git.md#merge-conflict"
    tools = [c["tool"] for c in data["tool_calls"]]
    assert "list_files" in tools
    assert "read_file" in tools


def test_documentation_agent_lists_wiki_files() -> None:
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "list_files", "arguments": json.dumps({"path": "wiki"})},
                            }
                        ],
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {"answer": "Here are the wiki files.", "source": "wiki/"},
                        ),
                    }
                }
            ]
        },
    ]

    server, port = _run_stub_server(responses)
    try:
        data = _run_agent("What files are in the wiki?", f"http://127.0.0.1:{port}/v1")
    finally:
        server.shutdown()

    tools = [c["tool"] for c in data["tool_calls"]]
    assert "list_files" in tools

