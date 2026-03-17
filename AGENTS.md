## Agents in this repository

This project is designed to be used with IDE assistants (Cursor, Qwen Code, etc.)
while you build and evolve `agent.py`. This file defines how those assistants
should behave when working in this repo.

## Core principles

1. **Follow the lab, not your defaults.** Prefer information from `wiki/`,
   `lab/tasks/required/`, and `docs/` over model priors.
2. **Respect plans.** Each lab task has a plan in `plans/task-N.md`. Stick to
   the chosen approach unless the user explicitly asks to change it.
3. **Be explicit, but concise.** Explain non-trivial design and trade-offs, but
   avoid rambling. Favor DRY and KISS in both prose and code.
4. **Bias for action.** When the user asks you to implement something, assume
   they want concrete changes (code, tests, docs) rather than only advice.
5. **Keep secrets safe.** Never print or commit contents of `.env.*.secret`
   files or any access tokens.

## How to answer questions

- **Check the repo first**:
  - `wiki/` for general background (LLMs, infrastructure, tooling).
  - `lab/tasks/required/` for task-specific requirements.
  - `docs/requirements/` and `docs/design/` for system behavior.
- If something is not documented, say so and describe what you searched.
- When explaining, prefer concrete examples derived from this codebase.

## How to change code

- **Before editing**:
  - Read the relevant task file in `lab/tasks/required/`.
  - Read the corresponding plan in `plans/task-N.md`.
  - Skim nearby files to understand existing patterns.
- **While editing**:
  - Keep implementations small and focused.
  - Match existing style (imports, error handling, logging).
  - Route debug/progress output in CLIs to `stderr`, not `stdout`.
- **After editing**:
  - Update or add tests to cover new behavior.
  - Run the appropriate tests or scripts when possible (for example,
    `pytest backend/tests/unit` or `uv run run_eval.py --index N`).

## Agent-specific guidance

- `agent.py` is the main CLI that talks to the LLM.
  - It must always print a single JSON object with at least `answer` and
    `tool_calls` fields to `stdout`.
  - All diagnostics and errors must go to `stderr`.
  - Configuration for the LLM comes from `.env.agent.secret`.
- `AGENT.md` documents how the current version of `agent.py` works. Keep it
  aligned with the implementation as you change behavior across tasks.

## Project structure (for assistants)

- `agent.py` — main agent CLI built across tasks 1–3.
- `AGENT.md` — documentation of the agent architecture and behavior.
- `plans/` — implementation plans (one per required task).
- `lab/tasks/required/` — official task descriptions and acceptance criteria.
- `wiki/` — shared documentation for tools, workflows, and background concepts.
- `backend/` — FastAPI backend used in later tasks.
- `frontend/` — frontend client (not directly used in Task 1).
- `.env.agent.secret` — LLM provider credentials (gitignored).
- `.env.docker.secret` — backend API credentials (gitignored).
