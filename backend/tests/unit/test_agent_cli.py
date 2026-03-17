import json
import subprocess
import sys
from pathlib import Path


def test_agent_cli_outputs_expected_shape() -> None:
    """agent.py should print JSON with 'answer' and 'tool_calls' keys."""
    project_root = Path(__file__).resolve().parents[3]
    agent_path = project_root / "agent.py"

    assert agent_path.exists(), "agent.py must exist at the project root"

    result = subprocess.run(
        [sys.executable, str(agent_path), "Test question"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"agent.py exited with {result.returncode}: {result.stderr}"

    stdout = result.stdout.strip()
    assert stdout, "agent.py must produce output on stdout"

    data = json.loads(stdout)

    assert "answer" in data, "Output JSON must contain 'answer'"
    assert "tool_calls" in data, "Output JSON must contain 'tool_calls'"
    assert isinstance(data["answer"], str)
    assert isinstance(data["tool_calls"], list)

