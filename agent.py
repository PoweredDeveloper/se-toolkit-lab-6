#!/usr/bin/env python3
"""CLI documentation agent with file-reading tools."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import httpx


def _load_llm_env(env_file: str = ".env.agent.secret") -> None:
    """Load LLM_* variables from a simple key=value env file into os.environ.

    Existing environment variables are not overwritten.
    """
    path = Path(env_file)
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _build_system_prompt() -> str:
    return (
        "You are a documentation assistant for this repository. "
        "You can use tools to inspect the local project wiki. "
        "When needed, first call list_files on the wiki directory to discover files, "
        "then call read_file to read relevant markdown. "
        "After gathering evidence, answer the user's question. "
        "Your final response MUST be a single JSON object with keys: "
        '"answer" (string) and "source" (string, a wiki section reference like '
        '"wiki/git.md#merge-conflict").'
    )


def _tool_schemas() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List files and directories at a given relative path.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file from the repository by relative path.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        },
    ]


def _call_llm(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Call the configured LLM and return its raw JSON response."""
    _load_llm_env()

    api_base = os.environ.get("LLM_API_BASE", "").rstrip("/")
    api_key = os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_MODEL", "")

    if not api_base or not api_key or not model:
        missing = [
            name
            for name, value in [
                ("LLM_API_BASE", api_base),
                ("LLM_API_KEY", api_key),
                ("LLM_MODEL", model),
            ]
            if not value
        ]
        print(
            f"Missing required LLM configuration variables: {', '.join(missing)}. "
            "Set them in .env.agent.secret or the environment.",
            file=sys.stderr,
        )
        sys.exit(1)

    url = f"{api_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
    }

    try:
        with httpx.Client(timeout=40.0) as client:
            response = client.post(url, headers=headers, json=payload)
    except httpx.RequestError as exc:
        error_msg = f"LLM request error: {exc}"
        print(error_msg, file=sys.stderr)
        print(
            json.dumps(
                {"answer": "", "source": "", "tool_calls": [], "error": "LLM request failed"},
                ensure_ascii=False,
            ),
            file=sys.stdout,
        )
        sys.exit(1)

    if response.status_code < 200 or response.status_code >= 300:
        short_body = response.text[:200]
        print(
            f"LLM returned non-2xx status {response.status_code}: {short_body}",
            file=sys.stderr,
        )
        print(
            json.dumps(
                {
                    "answer": "",
                    "source": "",
                    "tool_calls": [],
                    "error": f"LLM HTTP {response.status_code}",
                },
                ensure_ascii=False,
            ),
            file=sys.stdout,
        )
        sys.exit(1)

    try:
        return response.json()
    except ValueError:
        body_preview = response.text[:200]
        print(
            f"Failed to parse LLM JSON response: {body_preview}",
            file=sys.stderr,
        )
        print(
            json.dumps(
                {"answer": "", "source": "", "tool_calls": [], "error": "Invalid LLM JSON"},
                ensure_ascii=False,
            ),
            file=sys.stdout,
        )
        sys.exit(1)


def _project_root() -> Path:
    return Path(__file__).resolve().parent


def _validate_relative_path(rel_path: str) -> Tuple[bool, str]:
    if not isinstance(rel_path, str) or not rel_path.strip():
        return False, "Invalid path: must be a non-empty string."
    if Path(rel_path).is_absolute():
        return False, "Invalid path: must be relative."
    parts = Path(rel_path).parts
    if any(part == ".." for part in parts):
        return False, "Invalid path: parent traversal is not allowed."
    return True, ""


def _resolve_under_root(rel_path: str) -> Tuple[Path | None, str]:
    ok, error = _validate_relative_path(rel_path)
    if not ok:
        return None, error

    root = _project_root()
    resolved = (root / rel_path).resolve()
    try:
        if not resolved.is_relative_to(root):
            return None, "Invalid path: outside project directory."
    except AttributeError:
        # Python < 3.9 fallback (not expected, but safe).
        if str(resolved).startswith(str(root.resolve()) + os.sep) is False and resolved != root.resolve():
            return None, "Invalid path: outside project directory."
    return resolved, ""


def _tool_list_files(args: Dict[str, Any]) -> str:
    rel = (args or {}).get("path", "")
    resolved, error = _resolve_under_root(rel)
    if error:
        return error
    if resolved is None:
        return "Invalid path."
    if not resolved.exists():
        return f"Not found: {rel}"
    if not resolved.is_dir():
        return f"Not a directory: {rel}"

    entries = sorted(p.name for p in resolved.iterdir())
    return "\n".join(entries)


def _tool_read_file(args: Dict[str, Any]) -> str:
    rel = (args or {}).get("path", "")
    resolved, error = _resolve_under_root(rel)
    if error:
        return error
    if resolved is None:
        return "Invalid path."
    if not resolved.exists():
        return f"Not found: {rel}"
    if not resolved.is_file():
        return f"Not a file: {rel}"
    try:
        return resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "Error: file is not valid UTF-8 text."


def _execute_tool(tool_name: str, args: Dict[str, Any]) -> str:
    if tool_name == "list_files":
        return _tool_list_files(args)
    if tool_name == "read_file":
        return _tool_read_file(args)
    return f"Error: unknown tool '{tool_name}'."


def _parse_final_content(content: str) -> Tuple[str, str]:
    text = (content or "").strip()
    if not text:
        return "", ""
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            answer = str(data.get("answer", "")).strip()
            source = str(data.get("source", "")).strip()
            return answer, source
    except json.JSONDecodeError:
        pass
    return text, ""


def _run_agent(question: str) -> Dict[str, Any]:
    tools = _tool_schemas()
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": _build_system_prompt()},
        {"role": "user", "content": question},
    ]

    tool_calls_log: List[Dict[str, Any]] = []
    total_tool_calls = 0

    last_answer = ""
    last_source = ""

    while True:
        raw = _call_llm(messages, tools)

        message: Dict[str, Any] = {}
        try:
            choices = raw.get("choices") or []
            if choices:
                message = choices[0].get("message") or {}
        except (AttributeError, TypeError, IndexError):
            message = {}

        model_tool_calls = message.get("tool_calls") or []
        if model_tool_calls:
            for call in model_tool_calls:
                if total_tool_calls >= 10:
                    break
                fn = (call or {}).get("function") or {}
                tool_name = fn.get("name") or ""
                args_json = fn.get("arguments") or "{}"
                try:
                    tool_args = json.loads(args_json) if isinstance(args_json, str) else (args_json or {})
                except json.JSONDecodeError:
                    tool_args = {}

                result = _execute_tool(tool_name, tool_args)
                tool_calls_log.append({"tool": tool_name, "args": tool_args, "result": result})
                total_tool_calls += 1

                tool_call_id = (call or {}).get("id") or ""
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": result,
                    }
                )

            if total_tool_calls >= 10:
                break
            continue

        content = message.get("content") or ""
        last_answer, last_source = _parse_final_content(content)
        break

    if not last_answer:
        last_answer = "I could not generate an answer."
    if not isinstance(last_source, str):
        last_source = ""

    return {"answer": last_answer, "source": last_source, "tool_calls": tool_calls_log}


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: agent.py \"<question>\"", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]
    result = _run_agent(question)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

