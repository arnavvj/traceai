# Contributing to TraceAI

Thank you for your interest in contributing. TraceAI is an open-source project and contributions of all kinds are welcome — bug reports, feature requests, documentation improvements, and code.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Prerequisites](#prerequisites)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Testing](#testing)
- [Linting and Type Checking](#linting-and-type-checking)
- [Building the Dashboard](#building-the-dashboard)
- [Making Changes](#making-changes)
- [Pull Request Process](#pull-request-process)
- [Reporting Bugs](#reporting-bugs)
- [Requesting Features](#requesting-features)

---

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold it.

---

## Prerequisites

- Python 3.11 or higher
- `git`
- Node.js 18+ (only needed for dashboard changes)
- A virtual environment tool (`venv`, `uv`, or `conda`)

---

## Development Setup

```bash
# 1. Fork and clone the repository
git clone https://github.com/your-username/traceai.git
cd traceai

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3. Install in editable mode with all dev dependencies
pip install -e ".[dev]"

# 4. Verify the install
pytest --tb=short -q
traceai --help
```

---

## Project Structure

```
traceai/                  Python package
├── __init__.py           Public API surface
├── models.py             Pydantic models (Span, Trace, SpanKind, …)
├── tracer.py             Tracer, SpanContext, _ExperimentCM
├── storage.py            TraceStore (SQLite, sync + async)
├── server.py             FastAPI application and REST endpoints
├── cli.py                Typer CLI (list, inspect, export, open, …)
├── costs.py              Token cost estimation
├── integrations/
│   ├── __init__.py       instrument() dispatcher
│   ├── openai.py         OpenAI auto-instrumentation patch
│   └── anthropic.py      Anthropic auto-instrumentation patch
└── dashboard/            Pre-built React bundle (gitignored, included in wheel)

dashboard/                React dashboard source
├── src/
│   ├── App.tsx
│   ├── components/       UI components
│   ├── types/            TypeScript type definitions
│   ├── api/              API client
│   ├── hooks/            React hooks
│   └── utils/            Shared utilities
├── package.json
└── vite.config.ts

tests/                    Test suite
├── test_models.py
├── test_storage.py
├── test_tracer.py
├── test_server.py
├── integrations/
│   ├── test_openai_patch.py
│   └── test_anthropic_patch.py
└── conftest.py

examples/                 Runnable examples
docs/                     Documentation
assets/                   Logo and images
```

---

## Testing

```bash
# Run the full test suite
pytest

# Run with verbose output
pytest -v

# Run a specific test file
pytest tests/test_tracer.py

# Run tests matching a pattern
pytest -k "streaming or sampling"

# Run with coverage
pytest --cov=traceai --cov-report=term-missing
```

Tests use `pytest-asyncio` with `asyncio_mode = "auto"`, so async test functions work without any decorator.

The test suite does **not** require real API keys. Provider tests use `unittest.mock.patch` and `MagicMock` objects.

---

## Linting and Type Checking

All code must pass `ruff` (linting + formatting) and `mypy` (type checking) before merging.

```bash
# Lint
python -m ruff check .

# Auto-fix fixable issues
python -m ruff check --fix .

# Format check
python -m ruff format --check .

# Auto-format
python -m ruff format .

# Type check
python -m mypy traceai/
```

Configuration lives in `pyproject.toml` under `[tool.ruff]` and `[tool.mypy]`. The project uses `strict` mypy mode.

---

## Building the Dashboard

The dashboard is a React + TypeScript + Vite + Tailwind CSS app. You only need to touch this if you are changing dashboard UI.

```bash
# Install node dependencies
cd dashboard
npm install

# Development server with hot reload
npm run dev    # http://localhost:5173 — proxies API to localhost:7474

# Production build (output goes to dashboard/dist/)
# On Linux/macOS:
npm run build

# On Windows (use WSL):
wsl -e bash -c "cd /mnt/c/path/to/traceai/dashboard && npm run build"
```

The production bundle is committed to `traceai/dashboard/dist/` (gitignored but included in the wheel via `pyproject.toml` artifacts configuration).

---

## Making Changes

1. **Create a branch** from `main`:
   ```bash
   git checkout -b feat/your-feature-name
   ```

2. **Write tests first** (or alongside) your changes. The project aims to maintain comprehensive test coverage.

3. **Keep changes focused**. One feature or fix per PR makes review faster and easier to revert if needed.

4. **Follow existing conventions**:
   - Use `snake_case` for Python, `camelCase`/`PascalCase` for TypeScript.
   - Public Python functions need type annotations.
   - Async methods use the `a` prefix (e.g., `aget_trace`, `alist_traces`).
   - FastAPI endpoints live inside `create_app()` in `server.py`.

5. **Update `CHANGELOG.md`** under `[Unreleased]` with a brief description of your change.

---

## Pull Request Process

1. Ensure `pytest`, `ruff check`, `ruff format --check`, and `mypy` all pass locally.
2. If you changed the dashboard, run `npm run build` and commit the updated `dist/`.
3. Open a PR against `main` with a clear title and description.
4. Link any related issues using `Closes #123` in the PR body.
5. A maintainer will review and may request changes or ask questions.
6. Once approved and CI passes, the PR will be merged.

---

## Reporting Bugs

Open a [GitHub issue](https://github.com/arnavvj/traceai/issues/new?template=bug_report.md) using the bug report template. Include:

- TraceAI version (`pip show traceai`)
- Python version (`python --version`)
- OS and version
- Minimal reproduction steps
- Expected vs. actual behaviour
- Full error output / traceback

---

## Requesting Features

Open a [GitHub issue](https://github.com/arnavvj/traceai/issues/new?template=feature_request.md) using the feature request template. Describe the use case, not just the implementation — this helps us understand the problem you are trying to solve.
