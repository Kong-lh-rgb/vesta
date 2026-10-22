# Contributing to Vesta

Vesta is in local development. Please start with a focused issue or pull request;
interfaces and stored data may still change. Security reports should follow
[SECURITY.md](SECURITY.md), not a public bug report.

## Local setup

Use Python 3.12+, Node.js 22+, and npm. The Computer Helper and real Seatbelt
isolation need macOS with Swift tooling. On Linux, Shell and MCP launches that
require Vesta's Sandbox fail closed; this is expected.

```bash
git clone https://github.com/Kong-lh-rgb/vesta.git
cd vesta
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt
cp backend/.env.example backend/.env
cd desktop && npm ci
```

Configure a model only when exercising live functionality. Do not commit API
keys, `.env`, workspace data, traces, or generated artifacts. See the
[README quick start](README.md#quick-start) for CLI, Host, and Desktop startup.

## Checks

Run commands from the repository root unless shown otherwise:

```bash
cd backend
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/python -m compileall -q app tests

cd ../desktop
npm test
npm run typecheck
npm run build
```

On macOS, also run the real Sandbox tests and Native Helper checks:

```bash
cd backend
.venv/bin/python -m pytest tests/offline/sandbox/test_sandbox.py
cd ../native/macos-computer-helper
swift build
swift Tests/protocol_check.swift
```

The default pytest suite is offline and does not call paid model APIs. Live
evaluation is separate and must be run explicitly; see
[backend/tests/README.md](backend/tests/README.md).

## Changes and pull requests

- Follow nearby Python, TypeScript, and Swift style; keep changes scoped and
  add focused tests when behavior or a safety boundary changes.
- Keep the Sandbox fail-closed behavior, tool approvals, and secret filtering.
  Explain any platform-specific testing limits in the PR.
- Run the relevant checks above. In the PR, describe the change, verification,
  compatibility or data-format impact, and any untested paths.
- Link an existing issue when relevant. A maintainer reviews and merges PRs;
  there is no fixed response-time commitment.

See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
before adding copied code or assets. Include the upstream license and
attribution when required.
