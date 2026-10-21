Title: Add CryptoNyan mission bridge, Codex adapter and Asset Doctor

CryptoNyan asset missions can now be submitted through a local Python API, CLI or
MCP stdio service, persisted in SQLite, and dispatched to isolated fixture or Blender
workers. Each job snapshots its inputs and returns hashed quality reports. Opt-in
copy/naming repairs produce a separate review scene without saving over source files.
Cancellation, concurrency limits, total deadlines, bounded retries and revision
linkage make the delegation path reproducible.

An experimental local Codex app-server adapter connects structured missions to one
immutable Asset Doctor tool. It uses the user's normal ChatGPT sign-in, verifies a
read-only model sandbox, rejects scope changes and returns measured worker results.
The mock and direct Blender executors remain usable without model credentials.
Real authenticated model dispatch still requires local validation; the available
CLI's profile is read-only in this cloud environment.

Asset Doctor reuses Loopcut object summaries and UV mathematics and guards rigs,
modifiers and shape keys. All changes are new files; native Loopcut agent loops remain
unchanged. The architecture audit explains why enabling CODEX_SPEC and ORCH_SPEC does
not create nested orchestration. ComfyUI, Unreal 5.8, runner, animation and visual QA
modules define future contracts only.

Validation:

- 49 extension tests pass on Linux/Python 3.12.14, including three real Blender 4.3.2
  headless tests and scripted Codex subprocess protocol tests.
- 340 selected upstream regression tests pass with local dummy test configuration.
- Historical discovery on the retrieved subset ran 396 tests with two setup errors:
  this sandbox prohibits local HTTP sockets used by agent-loop/wave tests.
- The CLI mock example and MCP stdio lifecycle run successfully. Tests verify source
  hashes, geometry, independently saved copies, cancellation and artifact integrity.
- A Windows/Linux Python 3.11/3.13 workflow is included. See PR checks for CI results.

Required local follow-ups: Windows with actual Loopcut Blender 5.2.2, Claude Code
interoperability, authenticated Codex dispatch, ComfyUI/GPU and Unreal 5.8. Exact steps
and limits are recorded in [validation.md](validation.md) and
[codex-adapter.md](codex-adapter.md). ComfyUI/Unreal are not working integrations yet.

No automatic merge/import or production release. No live model call was made during
development. Inputs should be self-contained; linked dependency packaging and
crash-proof child supervision remain future work. GPL-3.0-or-later code; no upstream
trademark assets are reused for a new distribution.
