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
  processes. Computer control needs Accessibility permission; window screenshots
  need macOS 14+ and Screen Recording permission.
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
- The Electron build has not been validated as a packaged, signed, clean-machine
  application; source-run Desktop checks do not cover that distribution path.

## Validation before publishing

CI runs the Backend offline suite, Ruff, and compile checks on Linux; Desktop
tests, typecheck, and build on Linux; native Sandbox tests and Helper checks on
macOS. For commit `eb29312`, all four jobs passed in
[CI run 41954993018](https://github.com/Kong-lh-rgb/vesta/actions/runs/41954993018):
Backend, Backend macOS Sandbox, Desktop, and Native macOS.

On 2026-11-05, focused local Backend server/trace/memory tests passed
(190 tests), Desktop tests passed (250 tests), and Desktop typecheck and build
passed. Live-model evaluation, a full Desktop/Helper interaction on a clean
machine, and packaged-app testing remain unverified for this draft. Recheck
the final commit and record its CI result before publishing.

## Next work

Stabilize cross-platform process isolation, document data migration behavior,
expand release validation on clean machines, and collect issue feedback before
considering a stable release.
