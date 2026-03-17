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
    responses = []
    call_index = 0

    def log_message(self, format: str, *args) -> None:  # noqa: A002
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


class _StubBackendHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/items/":
            self.send_response(404)
            self.end_headers()
            return

        # Minimal auth check similar to backend (Authorization: Bearer <key>)
        auth = self.headers.get("Authorization", "")
        if auth != "Bearer test-backend-key":
            self.send_response(401)
            body = json.dumps({"detail": "Invalid API key"}).encode("utf-8")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        items = [{"id": 1, "external_id": "x"}, {"id": 2, "external_id": "y"}]
        body = json.dumps(items).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _run_server(handler_cls, responses=None):
    port = _free_port()
    if responses is not None:
        handler_cls.responses = responses
        handler_cls.call_index = 0
    server = HTTPServer(("127.0.0.1", port), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def _run_agent(question: str, llm_base: str, backend_base: str) -> dict:
    project_root = Path(__file__).resolve().parent.parent
    agent_path = project_root / "agent.py"

    env = os.environ.copy()
    env.update(
        {
            "LLM_API_BASE": llm_base,
            "LLM_API_KEY": "test-llm-key",
            "LLM_MODEL": "test-model",
            "AGENT_API_BASE_URL": backend_base,
            "LMS_API_KEY": "test-backend-key",
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


def test_system_agent_reads_source_for_framework() -> None:
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
                                "function": {
                                    "name": "read_file",
                                    "arguments": json.dumps({"path": "backend/app/main.py"}),
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
                            {"answer": "The backend uses FastAPI.", "source": "backend/app/main.py"}
                        ),
                    }
                }
            ]
        },
    ]

    llm_server, llm_port = _run_server(_StubChatHandler, responses=responses)
    backend_server, backend_port = _run_server(_StubBackendHandler)
    try:
        data = _run_agent(
            "What framework does the backend use?",
            f"http://127.0.0.1:{llm_port}/v1",
            f"http://127.0.0.1:{backend_port}",
        )
    finally:
        llm_server.shutdown()
        backend_server.shutdown()

    assert "read_file" in [tc["tool"] for tc in data["tool_calls"]]


def test_system_agent_queries_api_for_item_count() -> None:
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
                                "function": {
                                    "name": "query_api",
                                    "arguments": json.dumps({"method": "GET", "path": "/items/"}),
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
                                "answer": "There are 2 items in the database.",
                                "source": None,
                            }
                        ),
                    }
                }
            ]
        },
    ]

    llm_server, llm_port = _run_server(_StubChatHandler, responses=responses)
    backend_server, backend_port = _run_server(_StubBackendHandler)
    try:
        data = _run_agent(
            "How many items are in the database?",
            f"http://127.0.0.1:{llm_port}/v1",
            f"http://127.0.0.1:{backend_port}",
        )
    finally:
        llm_server.shutdown()
        backend_server.shutdown()

    assert "query_api" in [tc["tool"] for tc in data["tool_calls"]]

