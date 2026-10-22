# Draft: Vesta v0.x preview

**Review draft only. No tag, release, or distribution package has been made.**
The exact preview version and date require maintainer approval. Backend and
Desktop currently report `0.1.0`; this is not evidence of a stable release.

## Scope

This source preview provides a local Python Agent Host and CLI, an Electron
Desktop, and a macOS Computer Helper. Current features include multi-provider
model adapters, Task/Plan tracking, context and memory management, Run
checkpoints and recovery, local tools, stdio MCP, Skill Learning candidates,
automation, traces, usage, and artifacts. The
[README demo](README.md#demo) shows existing local runs.

## Requirements and start

- Python 3.12+ and Node.js 22+; npm is used for Desktop development.
- macOS and Swift tooling for Computer Helper and Seatbelt-isolated Shell/MCP
  processes. Accessibility permission is needed for Computer control.
- A configured model provider and API key for live Agent runs.

Follow the [README quick start](README.md#quick-start) to create a Backend
virtual environment, install requirements, configure the model, then start
the CLI or the Host and Electron Desktop. There is currently no packaged
installer or signed app in this repository.

## Known limits

- Intended for local single-user use; interfaces and stored data may change.
- On platforms without a Vesta Sandbox backend, constrained Shell and MCP
  launches fail closed. Explicit Host mode removes OS-level isolation.
- MCP primarily uses stdio. The macOS backend cannot enforce an allowed-domain
  list and rejects such a policy; container and domain-proxy backends remain
  future work.
- Skill Learning produces candidates that require human confirmation.
- Real-provider evaluations cost money and are outside the default offline CI.

## Validation before publishing

CI runs the Backend offline suite, Ruff, and compile checks on Linux; Desktop
tests, typecheck, and build on Linux; native Sandbox tests and Helper checks on
macOS. Record the actual result and commit SHA here before publication:

- Backend Linux: **passed** in run
  [39744190256](https://github.com/Kong-lh-rgb/vesta/actions/runs/39744190256)
- Backend macOS Sandbox: **failed** in the same run
  (`test_shell_tool_uses_workspace_sandbox`); root cause was a test-only
  defect — creating a socket is not filtered by macOS Seatbelt, so the old
  probe exited 0 inside the sandbox. Fixed by switching the probe to a real
  TCP connect against a locally listened port, with an unsandboxed positive
  control and an EPERM-vs-connection-refused distinction. Production sandbox
  policy is unchanged. **Pending a passing remote re-run.**
- Desktop: **passed** in the same run
- Native Helper: **passed** in the same run
- Live model and end-to-end Desktop run: **not yet validated for this draft**

Local development check on 2026-10-22 (macOS, Python 3.14; not the Linux CI
runner): Backend 1149 passed / 1 skipped, Desktop 249 passed, Desktop typecheck
and build passed, Swift build and protocol check passed. After the sandbox
network-probe fix on the same day, the full offline Backend suite is 1085
passed / 1 skipped and a mutation check confirmed the new network assertion
fails when the sandbox policy is weakened to unrestricted. These local results
do not replace a passing remote CI run or a clean-machine release check.

## Next work

Stabilize cross-platform process isolation, document data migration behavior,
expand release validation on clean machines, and collect issue feedback before
considering a stable release.
