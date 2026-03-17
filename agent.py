#!/usr/bin/env python3
"""Simple CLI agent that calls an OpenAI-compatible LLM and prints JSON."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

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
        "You are a concise assistant. "
        "Answer the user's question briefly in plain text. "
        "Do not mention tools or internal reasoning."
    )


def _call_llm(question: str) -> Dict[str, Any]:
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
        "messages": [
            {"role": "system", "content": _build_system_prompt()},
            {"role": "user", "content": question},
        ],
    }

    try:
        with httpx.Client(timeout=40.0) as client:
            response = client.post(url, headers=headers, json=payload)
    except httpx.RequestError as exc:
        error_msg = f"LLM request error: {exc}"
        print(error_msg, file=sys.stderr)
        print(
            json.dumps(
                {"answer": "", "tool_calls": [], "error": "LLM request failed"},
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
                {"answer": "", "tool_calls": [], "error": "Invalid LLM JSON"},
                ensure_ascii=False,
            ),
            file=sys.stdout,
        )
        sys.exit(1)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: agent.py \"<question>\"", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]

    raw = _call_llm(question)

    answer = ""
    try:
        choices = raw.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            answer = (message.get("content") or "").strip()
    except (AttributeError, TypeError, IndexError):
        answer = ""

    if not answer:
        answer = "I could not generate an answer."

    result = {"answer": answer, "tool_calls": []}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

