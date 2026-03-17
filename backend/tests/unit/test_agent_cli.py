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
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/chat/completions":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", "0"))
        _ = self.rfile.read(length) if length else b""

        body = json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {"answer": "Test answer", "source": "wiki/git.md#merge-conflict"}
                            ),
                        }
                    }
                ]
            }
        ).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_agent_cli_outputs_expected_shape() -> None:
    """agent.py should print JSON with 'answer', 'source', and 'tool_calls' keys."""
    project_root = Path(__file__).resolve().parents[3]
    agent_path = project_root / "agent.py"

    assert agent_path.exists(), "agent.py must exist at the project root"

    port = _free_port()
    server = HTTPServer(("127.0.0.1", port), _StubChatHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    env = os.environ.copy()
    env.update(
        {
            "LLM_API_BASE": f"http://127.0.0.1:{port}/v1",
            "LLM_API_KEY": "test",
            "LLM_MODEL": "test-model",
        }
    )

    result = subprocess.run(
        [sys.executable, str(agent_path), "Test question"],
        cwd=project_root,
        capture_output=True,
        text=True,
        env=env,
    )
    server.shutdown()

    assert result.returncode == 0, f"agent.py exited with {result.returncode}: {result.stderr}"

    stdout = result.stdout.strip()
    assert stdout, "agent.py must produce output on stdout"

    data = json.loads(stdout)

    assert "answer" in data, "Output JSON must contain 'answer'"
    assert "source" in data, "Output JSON must contain 'source'"
    assert "tool_calls" in data, "Output JSON must contain 'tool_calls'"
    assert isinstance(data["answer"], str)
    assert isinstance(data["source"], str)
    assert isinstance(data["tool_calls"], list)

