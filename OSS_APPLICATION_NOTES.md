# Open-source application evidence notes

**Working notes for a human application, not a submitted application.**
Snapshot: 2026-10-22 (Asia/Shanghai). Recheck GitHub counts and CI before
submitting because they can change.

## Verifiable evidence

- **Maintainer activity:** this checkout contains 165 commits through
  `bfdcee9` (2026-10-04), all attributed in Git history to `Linghang`.
  Attribution is commit metadata, not proof that every line was authored by
  one person. Recent commits cover Agent/Application assembly (`bfdcee9`),
  provider error redaction (`077db79`), Sandbox/MCP regression tests
  (`f768ed5`), and context tests (`ef70de5`).
- **Implementation:** [`backend/app`](backend/app), [`desktop/src`](desktop/src),
  and [`native/macos-computer-helper/Sources`](native/macos-computer-helper/Sources)
  contain the runtime, UI, and Computer Helper. The README explains their
  architecture and current limitations.
- **Automation:** [CI](.github/workflows/ci.yml) defines Backend pytest,
  Ruff and compile checks; Desktop Vitest, typecheck and build; macOS native
  Helper build/protocol check; plus a proposed macOS Sandbox test job. This
  local change is **not** a passing remote CI run until it is pushed and run.
- **Demonstration:** [`docs/assets/vesta-demo.gif`](docs/assets/vesta-demo.gif)
  and the README screenshots show a recorded local workflow. They do not
  establish production usage or an external user base.
- **Community signal:** the [public repository](https://github.com/Kong-lh-rgb/vesta)
  showed 66 stars and one fork in the GitHub page snapshot reviewed during
  this work; the user's more recent estimate is about 67 stars. No external
  adoption or download count has been verified. The connected GitHub issue
  and PR search returned no entries, so do not claim external contributor
  activity or confirmed community feedback.
- **Release status:** no local Git tags were present in this checkout. The
  [`RELEASE_NOTES_DRAFT.md`](RELEASE_NOTES_DRAFT.md) is a review draft, not
  evidence of a published release.

## Honest gaps to address

1. Confirm a passing remote Linux and macOS CI run on the intended commit.
2. Verify the source preview on a clean macOS machine, including permission
   prompts and an end-to-end model run, then document the result.
3. The resume images previously tracked under `tmp/pdfs/resume_optimized/`
   have been removed from the working tree. They remain in earlier Git history;
   decide separately whether historical exposure requires remediation. Confirm
   demo-image provenance before distribution and retain the Spec Kit notice.
4. Gather real issue reports and usability feedback over time. Avoid treating
   stars as proof of active users.

Possible application framing: Vesta is an actively developed local Agent
Harness with a multi-component implementation, recorded demo, and automated
offline checks. It is a preview-stage project whose cross-platform isolation
and release process are still being strengthened.
