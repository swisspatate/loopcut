# CryptoNyan Asset Studio MVP

**Validations sur ton PC : [checklist centralisée en français](local-pc-checklist.md).**
Elle regroupe Windows/Blender, Unreal, Claude Code/Codex, ComfyUI et les mesures GPU,
avec les étapes encore à développer séparées des vérifications locales.

La v0.23 ajoute les [connexions des agents](agent-connections.md) : panneau Blender
optionnel, profil local, configuration Claude/Codex à copier et diagnostic MCP/ComfyUI.
Le parcours s'inspire de Mixar et réutilise notre serveur ; [suivi des portages](mixar-integration.md).

La v0.22 ajoute [Image Workshop](image-workshop.md) : référence PNG, recette explicite
par l’agent, formes ou GLB local, scène Blender, audit, export et comparaison rendue.
Les workflows TRELLIS existants sont prioritaires pour la prochaine liaison ComfyUI ;
la v0.22 reçoit déjà leurs GLB conformes mais ne soumet pas de génération neuronale.

An opt-in mission bridge and Asset Doctor for CryptoNyanRun. It queues local asset
audits, runs isolated workers, persists results and offers MCP tools for an external
orchestrator. It does not alter Loopcut's native agent behavior.

**Pour améliorer ton jeu existant, commencer par [la passerelle projet](existing-project.md).**
La v0.12 ajoute l'inventaire local, la découverte des profils du projet et les demandes
de textures liées aux assets par empreinte SHA-256. Les kits et le personnage ci-dessous
sont des démonstrations optionnelles. L'application aux niveaux existants reste une
intégration locale distincte, avec les outils et les rigs déjà présents dans le jeu.

La v0.13 ajoute [l'inspecteur Unreal et les variantes de matériaux](unreal-material-variants.md) :
slots, paramètres et dépendances directes lus dans l'éditeur, puis textures, instance
héritée et copie de mesh pour revue. Le plan est accessible aux agents MCP. Les originaux
et les niveaux restent inchangés ; l'exécution et le rendu sous Unreal exigent une
validation locale. Les tests du module Unreal utilisent des doubles d'API.

La v0.14 ajoute le [diagnostic ComfyUI avant génération](comfy-preflight.md) :
`texture_preflight` vérifie les nœuds, choix de modèles et entrées/connexions du
profil via les métadonnées locales, avec le prompt et la seed envisagés. Il ne
lance aucun calcul ; les cas personnalisés sont signalés pour revue.

La v0.15 ajoute les [collections de textures](texture-collections.md) : 1–16 entrées
liées aux assets existants, un style/profil commun, des seeds stables, un prévol avant
chaque nouvelle soumission et une reprise par reçus. La collecte produit un index
de candidats pour les variantes Unreal ; la cohérence visuelle reste à valider.

Read [architecture.md](architecture.md), [validation.md](validation.md) and
[roadmap.md](roadmap.md). General input-rig adaptation and automated aesthetic QA remain
**contracts only**; the generated quadruped prototype below and the v0.22 reference
candidate renders are implemented.

La v0.16 ajoute [Animation Doctor](animation-doctor.md) pour les rigs et actions
Blender existants : mapping d'os, poses évaluées, contrôle de boucle/racine,
vitesses et appuis déclarés, puis candidats de repères pour les effets. L'audit
préserve la source. Les versions suivantes ajoutent les notifies, la capture directe
d'AnimSequence et des corrections limitées des poids sur copies.

La v0.17 ajoute le [Creative Director](creative-director.md) : notifies Niagara sur
copie d'animation, cutscenes Sequencer à caméras spawnables et assemblage de modules
de décor existants en carte de revue. Les plans sont liés aux hashes des assets et
au projet. Les adaptateurs éditeur sont implémentés et testés avec des doubles d'API ;
leur validation dans Unreal reste locale. Les graphes Niagara, les rigs et les niveaux
de production ne sont pas automatiquement remplacés.

La v0.18 ajoute [la capture des poses Unreal et Rig Doctor](rig-and-unreal-animation.md) :
lecture RAW d'AnimSequence dans le repère du composant, puis réutilisation d'Animation
Doctor ; audit des poids de meshes Blender liés au rig existant. Les indices suspects
et les sources sont traçables. Le lecteur Blender est testé avec un vrai runtime Linux ;
la qualification Unreal, les déformations et le personnage réel restent à vérifier
localement. L'audit seul n'applique aucune correction.

La v0.19 ajoute les [corrections de poids sur copie](rig-repair.md) : plan lié aux
hashes, normalisation et réduction bornée des influences, puis sauvegarde et réouverture
indépendante du candidat Blender. Verrous et groupes auxiliaires sont préservés ; les
sommets sans poids et les retraits excessifs restent à examiner. La qualité de la
déformation et l'adoption dans Unreal nécessitent une validation locale.

La v0.20 ajoute les [niveaux riches et tenues](rich-levels-and-wardrobe.md) :
décoration à seed, bâtiments, repères, ambiances, mécanismes et plateformes réutilisables,
accessoires sur sockets et vêtements liés au Skeleton existant. Le [worker de vêtement](garment-workflow.md)
ajuste/transfère les poids sur copie et inspecte des poses dans Blender. Les
[références ComfyUI](comfy-references.md) raccordent des PNG/masques UV à des profils
configurés, réutilisables par les agents et les collections de skins. Les adaptateurs
Unreal et l'inférence GPU exigent encore la validation locale documentée.

La v0.21 ajoute la [revue réversible des matériaux dans un niveau existant](level-material-review.md) :
inspection des composants sélectionnés, plan explicite, comparatif HTML des affectations,
appliquer/restaurer avec journal durable, contrôle des conflits et préservation exacte
des slots hérités. Les meshes et matériaux sources ne sont pas édités ; la carte change
en mémoire uniquement sur application explicite. La validation dans Unreal reste locale.

Version 0.11 adds the [creative toolkit](creative-toolkit.md): reusable architecture,
mountains, animated liquid/FX/weather, lighting presets, a weighted quadruped with four
IK legs and six GLB clips. The Unreal plugin adds elemental powers, reactive surfaces,
bounded effects/weather and a C++ UMG menu. Blender and engine-free rules are tested;
full UHT/plugin compilation and gameplay require local validation. These are prototypes.

Version 0.10 adds [agent-facing ComfyUI profiles](comfy-agent-profiles.md): six optional
MCP tools for profile discovery, idempotent submission, status, recovery, queued deletion
and verified Material Doctor collection. Models/workflows stay operator-configured;
live GPU generation still needs local acceptance.

Version 0.9 adds [PBR materials in world previews](world-pbr.md): explicit biome/module
assignments, packed base-color/roughness/metallic/normal maps, shared materials, bounded
texture snapshots and a separate appearance identity. This reuses Material Doctor and
the existing Blender PBR graph; automatic textured Unreal import remains blocked.

Version 0.8 adds [combined Blender world previews and geometry QA](world-preview.md):
shared meshes, per-instance biome materials, zone collections, a common animation
window, static/swept overlap diagnostics and connector checks. Geometry checks do
not certify Unreal collision or controller behavior.

Version 0.7 adds [world assembly and Unreal runtime review](world-runtime.md): connect
audited kits at matching ground-centre sockets, assign biome palettes, scatter off-track
posts, generate periodic PBR maps and place a world through a new Unreal actor/plugin.
Blender and portable paths are tested; the full UE plugin build and runtime require local acceptance.

Version 0.6 adds [layered paths, cyclic lifts and material themes](worlds-and-themes.md):
upper/lower side branches, actual Blender preview animation, explicit Unreal motion
tracks and audited asset-by-theme batch publications. Static route checks exclude
moving branches; the actual Unreal gameplay behavior still requires local acceptance.

Version 0.5 adds the [Runner module kit](runner-kit.md): seeded flat three-lane layouts,
analytical jump windows with landing/recovery propagation, seed scans, SVG review,
Blender module/preview generation, audited GLB publication and a neutral Unreal/PCG CSV.
General PCGEx graphs and actual character-controller validation remain local/future work.

Version 0.4 adds the [PBR and ComfyUI pipeline](material-pipeline.md): a local HTTP
client, durable generation receipts, Material Doctor bundles, material application to
a new Blender copy and GLB publication with embedded PNGs. Real Blender export/reimport
is tested; live GPU generation and Unreal textured import remain local acceptance work.

Version 0.3 adds [Asset Publisher](publisher.md): a real Blender static mesh export,
portable checked GLB/manifest, and an explicit local Unreal review importer. Blender
export/roundtrip is tested; Unreal execution still requires local UE 5.8 validation.

Version 0.2 introduced an experimental [local Codex app-server adapter](codex-adapter.md),
a no-model `probe-codex` command and real stdio client/server lifecycle tests. Its
wire protocol is verified against the generated CLI 0.163.0 schema and scripted
peers; an authenticated model turn still requires local validation.

## Run the complete mock example

From a complete Loopcut checkout, Python 3.11+; no pip installation, model account,
API key or Blender required for the mock:

```sh
export PYTHONPATH="$PWD/scripts/addons_core"
python3 -m cryptonyan_asset_studio \
  --workspace /tmp/cryptonyan-jobs \
  --asset-root docs/cryptonyan/examples/assets \
  run docs/cryptonyan/examples/mission.json
```

The result includes a durable task ID, per-input report, acceptance result and artifact
hashes. The fixture is an intentionally open triangle, so boundary edges are a warning.
This is a Claude-style structured mission through a **mock** Codex executor; no model ran.

```sh
python3 -m cryptonyan_asset_studio --workspace /tmp/cryptonyan-jobs show TASK_ID
python3 -m unittest discover -s loopcut/tests -p 'test_cryptonyan*.py' -v
```

Tests use temporary directories. Blender tests explicitly skip if `blender` is absent;
set `LOOPCUT_BLENDER` to test the actual Loopcut executable. No native C++ build is needed.

## Windows installation and headless use

Keep the full source checkout, including `scripts/addons_core/loopcut` (the reused inspectors).
This is a Python package/CLI, not a standalone add-on ZIP. Version 0.23 adds an
explicitly registered [connection sidebar](agent-connections.md) in Blender.
In PowerShell from the checkout:

```powershell
$env:PYTHONPATH = (Resolve-Path .\scripts\addons_core).Path
$env:LOOPCUT_BLENDER = 'C:\Tools\Loopcut\blender.exe' # set your actual executable
py -3.13 -m unittest discover -s loopcut/tests -p 'test_cryptonyan*.py' -v

py -3.13 -m cryptonyan_asset_studio `
  --workspace "$env:LOCALAPPDATA\CryptoNyanAssetStudio\jobs" `
  --asset-root .\docs\cryptonyan\examples\assets `
  run .\docs\cryptonyan\examples\mission.json
```

For your own **saved, self-contained** scene, create `mission.json`:

```json
{
  "inputs": ["cat.blend"],
  "target_assets": ["CatBody"],
  "constraints": {"timeout_seconds": 120, "max_attempts": 1, "repair_copy": false},
  "success_criteria": {"max_triangles": 50000, "allow_warnings": true}
}
```

```powershell
py -3.13 -m cryptonyan_asset_studio `
  --workspace "$env:LOCALAPPDATA\CryptoNyanAssetStudio\jobs" `
  --asset-root 'D:\CryptoNyan\AssetsToAudit' `
  --executor blender --blender "$env:LOOPCUT_BLENDER" run .\mission.json
```

Omit `target_assets` to inspect all scene objects. The same targets apply to every input
in a multi-file mission; missing targets fail explicitly. `repair_copy: true` permits
only copying/naming/organization of unguarded meshes, returning `repaired-N.blend` in
the task directory. Source objects and files are never replaced. Inspect the report
and returned scene before using a copy. Repaired scenes contain originals **and** copies.

Audit every matching file directly in an input directory (non-recursive):

```powershell
py -3.13 -m cryptonyan_asset_studio `
  --workspace "$env:LOCALAPPDATA\CryptoNyanAssetStudio\batch" `
  --asset-root 'D:\CryptoNyan\AssetsToAudit' `
  --executor blender --blender "$env:LOOPCUT_BLENDER" --workers 2 batch
```

Without `--executor blender`, batch processes `.json` fixtures. `--repair-copy` is
available on batch but is rejected by the mock executor. CLI exit codes: 0 = audit
completed and criteria passed; 1 = worker failure or failed asset criteria; 2 = setup
or input error. Cancellation/control of running missions uses the long-lived MCP service.

## Explicit local MCP configuration

The stdio server opens **no TCP listener**. Configure it in the external MCP client
(for example Claude Code), adapting all paths to your checkout:

```json
{
  "mcpServers": {
    "cryptonyan-assets": {
      "command": "C:\\Python313\\python.exe",
      "args": [
        "-m", "cryptonyan_asset_studio",
        "--workspace", "C:\\CryptoNyan\\jobs",
        "--asset-root", "D:\\CryptoNyan\\AssetsToAudit",
        "--executor", "blender",
        "--blender", "C:\\Tools\\Loopcut\\blender.exe",
        "serve"
      ],
      "env": {"PYTHONPATH": "C:\\src\\loopcut\\scripts\\addons_core"}
    }
  }
}
```

Use the mock executor and fixture asset directory for a first client check. Stdio
authorization is the local user's explicit launch and access to the configured roots.
Do not expose stdio via an unauthenticated network relay. Any future HTTP transport
must default to loopback and implement authentication/authorization before network use.
Real Claude Code interoperability is pending; protocol request/response paths are tested.

| Tool | Arguments | Behavior |
| --- | --- | --- |
| `mission_submit` | `mission` object | Validate, snapshot, queue; returns a task ID immediately after snapshots. |
| `mission_query` | `task_id` | Read state, attempts, timestamps, error and artifact metadata. |
| `mission_cancel` | `task_id` | Idempotent cancellation; await `cancelled` for a running task. |
| `mission_revise` | `task_id`, complete `mission` | Terminal task only; creates a new ID linked to its predecessor. |
| `mission_result` | `task_id` | Completed task only; verifies artifact hashes before returning JSON. |

The client should poll at a modest interval (e.g. one second), stop on a terminal state,
and inspect `quality_passed`, not just `state`. Closing stdin shuts down the service
and cancels outstanding jobs. Records remain available through `show` and the Python API.
Only one service may own a workspace; use separate workspaces for independent sessions.

Enabling `LOOPCUT_CODEX_APP` and native orchestration together does not connect these
tools. Upstream explicitly disables the user's MCP servers in its Codex app-server
command. The independent adapter uses explicit dynamic-tool dispatch and the user's
normal Codex sign-in. The adapter described in
[codex-adapter.md](codex-adapter.md) implements that narrow mission dispatch outside
the live Loopcut UI. No undocumented Codex Cloud API is used here.

## Python adapter API

```python
from cryptonyan_asset_studio.bridge import MissionBridge
from cryptonyan_asset_studio.executors import MockCodexExecutor

with MissionBridge('/tmp/crypto-jobs', '/path/to/fixture-assets', MockCodexExecutor()) as bridge:
    task = bridge.submit({'inputs': ['triangle.json']})
    state = bridge.wait(task['id'], timeout=30)
    result = bridge.result(task['id'])  # raises if execution did not succeed
```

`CodexExecutor` specifies the seam implemented by the experimental `CodexAppServerExecutor`.
Implementations must honor deadlines/cancellation and write only inside their assigned
attempt directory. Built-in workers receive no model credentials and run only the
fixed Asset Doctor entry point. The SQLite database is the authoritative durable task
record; `Store.events(task_id)` returns structured, secret-free lifecycle events.

Keep input/workspace directories private. Process isolation and path checks do not
make untrusted Blender files or third-party plugins safe to execute. This MVP disables
auto-execution, uses factory startup, and does not run arbitrary mission-supplied code.
