# Native Loopcut briefs and desktop coordination

This optional local bridge dispatches a human-authorized brief into the existing
Codex chat in the visible Loopcut Blender panel. The desktop mailbox can delegate
to an operator-selected Codex conversation without starting a second model runner.
It does not install accounts, models, GPU software or a network listener.

All account settings, paths, prompts, receipts, databases, workflows, profiles and
session IDs are private operator data outside this repository. This document uses
aliases only: `SOURCE_ROOT` is this checkout and `WORK_ROOT` is a separate workshop.
Examples below are templates, not executable local configurations.

## Private bridge configuration

Create a private JSON file with exactly these fields, replacing aliases with
absolute paths on the operator's machine:

```json
{
  "schema": "loopcut.native-brief-bridge/1",
  "root": "<WORK_ROOT>/bridge",
  "work_root": "<WORK_ROOT>",
  "comfy_profiles": "<PRIVATE_CONFIG_ROOT>/comfy-profiles.json",
  "protected_roots": ["<GAME_ROOT>", "<ORIGINAL_WORKFLOWS_ROOT>", "<MODEL_ROOT>"]
}
```

Use a private directory accessible only to the operator. Paths are checked against
the workshop and protected roots; these checks are not a sandbox for the native
model's existing filesystem permissions. The model must preserve source scenes,
game assets, original workflows and models. Overwrites/deletions need human consent.

Launch the existing connection profile through the optional entry point:

```text
<PYTHON> -I <SOURCE_ROOT>/scripts/addons_core/cryptonyan_asset_studio/native_loopcut_mcp.py
  --bridge-config <PRIVATE_CONFIG_ROOT>/bridge.json
  --config <EXISTING_AGENT_CONNECTION_PROFILE> --client claude
```

On Blender's main thread, with native Codex mode enabled, install the receiver:

```python
from loopcut import native_brief_receiver
native_brief_receiver.install(operator_bridge_config_path)
```

Do not reload/uninstall it during an owned native turn. Installation takes a single
consumer lock. The receiver waits for a manual turn to finish, pins the active scene
and conversation, and calls the existing native `agent.send`. It never injects a
note into another turn. A timer tracks the actual owned thread and outcome.

The MCP tools are `loopcut_bridge_status`, `loopcut_brief_submit`,
`loopcut_brief_status` and `loopcut_brief_cancel`. Read readiness first and pass the
exact `session` and `scene` to `expected_session` and `expected_scene`. Untitled
scenes use an empty string. A changed target is rejected, not silently retargeted.

Stable IDs and exact arguments deduplicate submissions. Interrupted dispatches are
never requeued automatically. Inspect receipts and partial outputs before a new
mission. Cancellation targets only the owned turn and remains pending until it
stops. Receiver errors retain ownership while cancellation is in progress.

A `save_post` event may move the active filename only inside the current mission's
own output folder, while the same native turn owns it. This allows saving an
untitled candidate without cancelling its own mission. Loading another file or
saving outside that output still counts as a changed target; it is not a general
retarget permission.

`native_brief_cli.py --bridge-config <private-file> status|submit|get|cancel` uses
the same queue when an already-open client has cached its MCP tools. Brief files
must be bounded and inside the workshop. CLI output is UTF-8, including on Windows.

## Optional desktop mailbox and Claude context hook

Put `desktop-relay.json` next to the private bridge configuration to opt in:

```json
{
  "schema": "cryptonyan.desktop-relay/1",
  "thread_id": "<OPERATOR_SELECTED_EXISTING_CHAT_UUID>",
  "bridge_config": "<PRIVATE_CONFIG_ROOT>/bridge.json",
  "queue_config": "<PRIVATE_CONFIG_ROOT>/desktop-queue.json",
  "enabled": true
}
```

`desktop-queue.json` has the bridge schema above, with a different `root` below the
same workshop. The mailbox never starts or messages a model process by itself.
The operator separately configures a scheduled follow-up of that existing desktop
chat. Only that chat's ID can claim a mission. Do not run a second consumer against
another loaded copy of the scene.

The additional MCP tools are `codex_desktop_status`, `codex_desktop_submit`,
`codex_desktop_result` (wait 0–45 seconds) and `codex_desktop_cancel`. Submit to one
route only. An active Claude orchestrator waits for the same ID to receive the final
report; a stored report does not wake a closed/inactive Claude session.

The desktop consumer uses `desktop_relay.py --config <private-file> next --thread-id
<selected-id>`. Persist the stable native request ID with `progress` before native
submission. A recovered active claim is returned as `resume_inspect_first`, never
automatically executed again. Check its native receipt before any further action.

Finalize with `finish`, the claim token, a terminal status and a private report file.
Reports have exactly `summary` (string), `changes`, `objects`, `checks`,
`remaining_errors`, `outputs` and `recommendations` (lists). Output paths must stay
in the workshop. Final reports are immutable; identical reads/repeats are supported.
The token is not returned by the public MCP result tools.

An optional Claude command hook can run:

```text
<PYTHON> -I <SOURCE_ROOT>/scripts/addons_core/cryptonyan_asset_studio/claude_sync_hook.py
  --relay-config <PRIVATE_CONFIG_ROOT>/desktop-relay.json
```

Register it for `SessionStart` and `UserPromptSubmit` in the operator's private
Claude settings. It adds context for workshop/repository sessions or a Loopcut
request, then remembers only that session UUID and a timestamp. Unrelated sessions
are ignored. It grants no permissions, submits no task, calls no model and retains
no prompt/transcript. Optional failures do not block the human prompt. An operator
protocol may live beside the configuration as `SYNCHRONISATION-AUTO.md`.

## Existing native configuration and ComfyUI

Native Codex role loading does not require HTTP worker credentials. Child app-server
configuration removes incompatible desktop-only MCP transports without rewriting
global account settings. Optional `LOOPCUT_CODEX_CONTEXT_WINDOW` and
`LOOPCUT_CODEX_AUTO_COMPACT_TOKEN_LIMIT` affect only the child. The UI distinguishes
configured capacity from the effective window reported by Codex; it does not use
the HTTP loop's budget for a native conversation.

`LOOPCUT_BLENDER_PROFILE` optionally names an operator-owned absolute Python startup
file for background Blender children. No hardware preset or private script is
bundled. Leaving it unset retains the existing behavior.

`workshop_comfy.py --bridge-config <private-file> --workspace <new-workshop-folder>`
offers `profiles`, `preflight`, `submit`, `status`, `collect` and `inspect` using the
existing approved TextureService. Only submit when the human's task authorizes it.
No installation or GPU test is implied by a successful connection/preflight.
Collection normalizes Windows subfolder separators and still rejects absolute,
UNC and traversal paths. No global ComfyUI interrupt is used.

## Limits and extension points

An execution receipt is not visual, animation, licensing or Unreal validation.
Only report checks that actually ran. Do not claim native/desktop clients have
refreshed their tools merely because a fresh diagnostic client connected.

Artifact listing/image retrieval, parent-linked brief revisions and pre-edit scene
checkpoints are separate follow-up features. They are not implemented by this
baseline. Retain the existing queues and public tool schemas when extending them.

## Validation of this baseline

The focused CPU-only suite passed on Windows with Python 3.13: **216 tests,
0 failures, 0 errors, 1 skipped**. It covers the native app-server protocol with a
scripted peer, context reporting, Windows ComfyUI output paths, profile/review
contracts, native queue ownership, desktop reports and the portable Claude hook.
Run it from `loopcut/tests`:

```text
python -m unittest test_codex_app test_cryptonyan_codex test_layout
  test_codex_context_limits test_cryptonyan_comfyui test_cryptonyan_comfy_profiles
  test_cryptonyan_texture_review test_cryptonyan_native_briefs
  test_cryptonyan_desktop_relay test_cryptonyan_claude_sync_hook
  test_workspace.PureTest.test_hardware_profile_is_optional_and_uses_an_existing_absolute_python_file
```

The lines above form a single command. Adding the full `test_conversations` and
`test_workspace` suites produced **297 tests, 13 failures, 6 errors, 3 skipped**.
Those 19 failing test names match an unmodified `main` source snapshot at
`2edb493a702573c55c686daf93823d66eac1b6e9` (81 tests, 13 failures, 6 errors,
2 skipped in those two suites alone). They include platform-specific shell and
path fixtures. They are not marked passing or silently skipped by this branch.
The current two suites have 82 tests because of the added profile validation test.

These tests do not establish GPU generation, artistic quality, native client tool
refresh or unattended scheduled delivery. Validate those separately against the
operator's running installation, without publishing its configuration or receipts.
