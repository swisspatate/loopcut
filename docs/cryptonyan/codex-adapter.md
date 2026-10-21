# Experimental local Codex adapter (v0.2)

`CodexAppServerExecutor` implements the existing executor protocol using the local
Codex CLI's experimental app-server. It dispatches the fixed Asset Doctor worker
through a dynamic tool. It is not a Codex Cloud API and does not modify Loopcut's
native `CODEX_SPEC`, `ORCH_SPEC`, approvals or merge loop.

## What is implemented and what was tested

- Wire fields follow Loopcut's existing `codex_app.py` and were verified against
  `codex-cli 0.163.0 app-server generate-json-schema --experimental` in this environment.
- The stdio client initializes the server, reads account metadata without proactive
  token refresh, starts an ephemeral read-only thread, starts one turn, handles the
  fixed audit tool, and accepts results only after a completed turn.
- The real CLI's startup probe was attempted, but its normal profile resides on a
  read-only filesystem in this cloud, so it exited before handshake. **No real model
  turn or live authenticated dispatch has been validated.** No alternate credentials
  or profile were created to work around that restriction.
- Scripted app-server subprocess tests cover success and failure paths. A separate
  integration test delegates from that scripted peer into **real Blender 4.3.2**.
- The MCP CLI is exercised by a real subprocess stdio client using all five tools.
  Actual Claude Code client compatibility remains to be checked on the user's machine.

## Local Windows procedure

Use the existing Codex CLI installation and normal sign-in. The adapter reads only
account type, not login tokens; it never copies auth files or starts a login flow.
Open PowerShell in the full Loopcut checkout:

```powershell
$env:PYTHONPATH = (Resolve-Path .\scripts\addons_core).Path
$codexBinary = (Get-Command codex.exe).Source
$blenderBinary = 'C:\Tools\Loopcut\blender.exe'

py -3.13 -m cryptonyan_asset_studio `
  --workspace "$env:LOCALAPPDATA\CryptoNyanAssetStudio\codex-jobs" `
  --codex "$codexBinary" probe-codex
```

`probe-codex` performs initialization and `account/read` only. It does not create a
thread, submit a model turn, or emit account email/plan details. It exits 0 when the
protocol responds and a ChatGPT account is present, 1 when sign-in is missing, and
2 on startup/protocol failure. A successful probe does not prove network/model access.
If your installation exposes a shell wrapper instead of a native executable, locate
the underlying native Codex executable; the adapter does not invoke a command shell.

After a successful probe, use the `.blend` mission example from README:

```powershell
py -3.13 -m cryptonyan_asset_studio `
  --workspace "$env:LOCALAPPDATA\CryptoNyanAssetStudio\codex-jobs" `
  --asset-root 'D:\CryptoNyan\AssetsToAudit' `
  --executor codex --codex "$codexBinary" --blender "$blenderBinary" `
  run .\mission.json
```

This command **does call Codex** through the user's account and may consume its usage
allowance. The default mock and direct Blender modes still make no model requests.
`--codex-model` optionally selects a model; otherwise the user's configured model is
used. `--codex-home` selects an existing profile only when explicitly supplied; by
default the normal `CODEX_HOME`/user profile is preserved. API-key account types are
rejected in this first implementation to avoid unintentionally changing billing mode.

For Claude Code, use the README MCP configuration, set `--executor` to `codex`, and
add `--codex` with its absolute executable path. Keep the `--blender` option. The
flow is external MCP client -> mission queue -> local Codex app-server -> dedicated
audit tool -> isolated Blender -> measured JSON result. Each layer has a different
responsibility; merely enabling both native Loopcut modes still does not nest them.

## Execution boundary

The only supplied dynamic tool is `cryptonyan_asset_doctor`, accepting an empty
object. Its mission and inputs are already validated/snapshotted by the bridge.
Unknown tools and arguments are rejected. Repeated calls return the same measured
summary, with one worker run per attempt and at most eight successful tool requests.
The model cannot widen the mission, choose paths or submit Python through that tool.

Codex runs in a read-only thread with no approval escalation. The adapter checks the
reported sandbox and policy before sending the turn, declines native approval
requests, disables configured MCP servers and the shell/browser/plugin/multi-agent
features, and does not grant a danger-full-access fallback. These settings are
version-sensitive; validate the installed CLI when upgrading. Blender runs outside
that Codex sandbox under the existing per-job snapshot/output contract.

Quality comes from the worker artifact, never from the model's final prose. The
adapter adds `codex-dispatch.json` with dispatch counts/provenance; it does not retain
model prose, email, account details, or raw JSON-RPC transcripts. The Codex CLI itself
may retain its normal local diagnostics/account state; the bridge does not control
the user's CLI storage settings. Existing proxy and CA settings are preserved for
Codex; model API-key environment variables are not forwarded to it or Blender.

RPC lines are bounded to 1 MiB, the reader queue to 64 messages and a session to
10,000 received messages. A single total mission deadline includes Codex, Blender
and retries. Cancellation attempts `turn/interrupt` and then terminates the local
process; the worker uses the same cancellation event. No automatic retry of model
failures is enabled. Interrupted attempts do not publish partially measured results.

## Still required

Validate with the actual Windows CLI/sign-in, Blender 5.2.2 and Claude Code client.
Exercise cancellation while Blender is busy and while Codex is waiting for network.
Windows process-tree/crash supervision remains a local validation and hardening task;
there is no Windows Job Object implementation yet. This adapter is bounded Asset
Doctor delegation, not a general multi-specialist asset-building agent. Native
Loopcut ownership/merge integration and ComfyUI remain later milestones. Version 0.3
also dispatches immutable `asset_publish` missions through this same tool; publication
returns a checked bundle and never runs Unreal. See [publisher.md](publisher.md) for
the separate local Unreal review importer and its pending engine validation.
