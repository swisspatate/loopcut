Title: Add static Asset Publisher and explicit Unreal review importer

CryptoNyan can now publish one named static mesh from a saved Blender scene through
the existing mission queue, CLI, MCP service or Codex dispatcher. The isolated worker
audits the source, bakes rotation/scale on copied geometry, exports a GLB using Loopcut's
existing helpers, checks its geometry and produces a portable hashed manifest/report.
The source .blend is never saved.

The new Unreal script plans without engine access by default. Explicit apply inside a
local 5.8 editor probes APIs, reserves a new content-addressed review folder, requests
an import without overwrite/save, validates returned geometry/bounds/material binding/
LODs/collision and only then saves. Receipts preserve actual imported paths and partial
failure information. Engine API execution remains unvalidated; simulated tests are
clearly labeled.

Supported first asset: one independent static mesh, scene unit scale 1, one constant
opaque Principled material (or an explicit default on the copy). Rigs, modifiers,
hierarchy, mirrored transforms, textures and procedural/multiple materials are rejected.
No automatic Unreal launch, reimport, destructive rollback, ComfyUI generation, gameplay
collision, animation, production merge or release is added.

Validation:

- 73 local extension tests pass: 66 portable and seven real Blender 4.3.2 headless tests.
- A real asymmetric GLB roundtrip checks copied transforms, pivot geometry and material
  parameters. Source hashes remain unchanged. Scripted Codex dispatches the real worker.
- Standalone CLI publish -> hashed package -> Unreal dry-run plan completes successfully.
- 340 selected upstream regression tests pass. Native Loopcut source remains unchanged.
- Windows/Linux Python 3.11/3.13 and complete-checkout CI run on this pull request.
- Unreal tests cover validation-before-save, path/receipt protection, existing folders,
  incorrect version/APIs, tampering, scope escape and partial save failure using a fake API.

See [publisher.md](publisher.md) for exact PowerShell/editor-console commands, the
asymmetric local acceptance fixture, manifest contract, Epic API references and recovery
limits. Required local checks: actual Loopcut on Windows, Unreal 5.8 glTF/Interchange
execution and visual material/pivot inspection. Authenticated Codex remains a separate
local validation. Editor import is synchronous and not controlled by the Blender queue.
