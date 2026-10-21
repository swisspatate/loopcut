# Animation Unreal et poids du rig existant — v0.18

Deux outils en lecture seule complètent [Animation Doctor](animation-doctor.md).
Ils examinent les assets sélectionnés et produisent des rapports locaux. Ils ne
normalisent pas les poids, ne reconstruisent pas le squelette et ne sauvegardent
aucun asset source. Ces commandes Python peuvent être invoquées par ton agent local ;
elles n'ajoutent pas de nouvel outil MCP ni de nouveau type de mission.

## Lire une AnimSequence directement dans Unreal

Il n'est plus nécessaire d'exporter un `.blend` pour analyser la **pose d'un clip**.
Copier [unreal-animation-capture.json](examples/unreal-animation-capture.json) hors du
projet et renseigner le chemin de l'AnimSequence, la racine et les vrais noms d'os.
Les exemples sont fictifs, sans assets privés de CryptoNyanRun.

Dans Unreal **5.8**, activer Python Editor Script Plugin et les fonctions éditeur
d'animation exposant `AnimPoseExtensions` (module AnimationBlueprintLibrary).
Enregistrer ou abandonner les modifications de contenu en attente, puis lancer sur
le thread éditeur, avec un seul agent propriétaire de la session :

```python
import sys
sys.path.insert(0, r"C:\Dev\loopcut\scripts\addons_core")
from cryptonyan_asset_studio.animation_doctor import read_json
from cryptonyan_asset_studio.unreal_animation import capture

report = capture(
    read_json(r"C:\CryptoNyanReviews\unreal-animation-capture.json"),
    r"C:\CryptoNyanReviews\run-audit-001",  # dossier neuf, hors projet
)
print(report["status"], report["findings"])
```

Sorties : `trace.json`, `audit.json`, `events.json`, `capture.json`. Le reçu conserve
un état d'échec si la capture échoue. Les fichiers `.uasset`, `.uexp` et `.ubulk`
présents de l'animation et du squelette sont hashés avant/après ; un changement de
source, de projet ou du contenu non enregistré interrompt la capture. Les dépendances
transitives, plugins et fichiers moteur ne sont pas intégralement hashés.

Le lecteur utilise `AnimDataEvalType.RAW`, sans retargeting ni évaluation de courbes,
avec incorporation du mouvement racine et sans extraction séparée de root motion.
Il échantillonne le clip entier, de zéro à sa durée, aux intervalles réguliers définis
par `sample_count`. `rate_scale` est enregistré, mais n'est pas appliqué : les secondes
du rapport sont celles de la timeline source. Animations additives/héritées, échelles
d'os différentes de 1 et chemins redirigés sont refusés.

**`AnimPoseSpaces.WORLD` désigne ici le repère du composant.** Aucune trajectoire
d'acteur en jeu n'est disponible. La trace porte donc `space: component` et exige
`contact_space: unknown`. Les contacts restent `not_assessed_unknown_world_motion` ;
ils ne peuvent pas alimenter automatiquement les contacts validés du Creative Director.
Le réaudit refuse également de qualifier ces traces comme des contacts mondiaux.
Les traces antérieures sans champ `space` restent compatibles.

Les positions sont converties de centimètres en mètres et Y est inversé pour obtenir
un repère droit. Un quaternion Unreal XYZW devient WXYZ `[w, -x, y, -z]` ; les rotations
relatives à la racine suivent cette même conversion. La comparaison de deux traces
Blender/Unreal requiert encore un alignement explicite de leurs axes et poses de base.

Limites : 2–2001 poses, 600 secondes, 512 os dans la pose et 64 os sélectionnés plus
la racine. Intervalle minimal 1 microseconde. Budgets existants de fichiers :
512 MiB par package, 1 GiB pour l'inspection. L'évaluation reste synchrone dans
l'éditeur : commencer par 31 poses, sans autres agents éditeur concurrents.

Ce lecteur ne mesure pas AnimBlueprint, Control Rig, IK runtime, physique, déformation
du mesh, compression cuite ou vitesse réelle de déplacement. `engine_validated: false`
et `unreal_runtime: false` signalent l'absence de qualification de cette intégration
dans un moteur réel ; une capture réussie ne certifie pas la qualité de l'animation.

## Examiner les poids du personnage dans Blender

Copier [rig-audit.json](examples/rig-audit.json), renseigner l'armature et chaque mesh
à examiner. Les noms sont ceux de ton personnage, sans convention imposée.

```powershell
$env:PYTHONPATH = "C:\Dev\loopcut\scripts\addons_core"
python -m cryptonyan_asset_studio.rig_doctor capture `
  C:\CryptoNyanReviews\character.blend C:\CryptoNyanReviews\rig-audit.json `
  --blender "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe" `
  --output C:\CryptoNyanReviews\rig-audit-001
```

Le processus Blender isolé ouvre une copie, avec scripts automatiques désactivés.
Sorties : `source.blend`, `request.json`, `weights.json`, `audit.json`.
Les hashes de la source et de sa copie sont contrôlés après le worker. Pour rejouer
l'analyse hors Blender avec d'autres seuils :

```powershell
python -m cryptonyan_asset_studio.rig_doctor audit `
  C:\CryptoNyanReviews\rig-audit-001\weights.json C:\CryptoNyanReviews\rig-audit.json `
  --output C:\CryptoNyanReviews\rig-audit-002
```

Codes de sortie : `0` aucun constat dans le périmètre, `1` constats à examiner,
`2` erreur ou entrée non prise en charge. Les dossiers de sortie existants sont refusés.

| Diagnostic | Interprétation |
|---|---|
| `unweighted_vertices` | Aucune influence d'un os déformant au-dessus de `weight_epsilon` |
| `weight_sum` | Somme des poids déformants différente de 1 au-delà de `sum_tolerance` |
| `too_many_influences` | Plus d'influences significatives que `max_influences` |
| `invalid_weights` | Valeur hors de l'intervalle [0,1] dans un instantané |

Chaque constat contient le nombre total et au plus 100 indices de sommets. Les groupes
de masque et les os avec `use_deform: false` sont listés séparément ; ils ne sont pas
comptés comme influences déformantes. Les groupes déformants inutilisés sont listés
à titre informatif. Un poids non normalisé n'implique pas à lui seul un défaut visible :
Blender et l'importeur peuvent traiter les sommes différemment. Le seuil de quatre
influences est un **budget configurable**, pas une limite universelle d'Unreal.

Le lecteur exige un seul modificateur Armature actif par mesh, ciblant l'armature
choisie et utilisant les groupes de sommets. Enveloppes, masque du modificateur et
multi-modifier sont refusés. Les autres modificateurs et la présence de shape keys
sont consignés, mais pas évalués. L'audit porte sur les poids du mesh de base.

Budgets combinés : 32 meshes, 200 000 sommets, 200 000 affectations de poids,
512 os, 1 024 groupes par mesh, `.blend` autonome ≤512 MiB, JSON ≤32 MiB,
worker 120 s par défaut (maximum 600 s). Réduire la sélection si elle dépasse un budget.

## Validation locale à effectuer

- Dans Unreal 5.8, comparer au moins trois poses au viewport : un os avec rotation
  non nulle, la racine et une patte. Vérifier unités, axes, durée, pose au dernier
  échantillon et options de root motion (`enable_root_motion`, `force_root_lock`).
- Vérifier qu'une animation in-place laisse les contacts non évalués, puis contrôler
  la capture d'un clip root-motion. Ne pas assimiler RAW à la lecture en PIE.
- Avec Blender Windows, exécuter les tests ci-dessous puis examiner les indices
  signalés dans Weight Paint/Edit Mode sur une copie de ton personnage.
- Comparer les SHA-256 source avant/après. Faire ensuite un test visuel des déformations
  en poses extrêmes et une vérification de l'import Unreal : ces résultats restent
  distincts du rapport de poids.

```powershell
$env:LOOPCUT_BLENDER = "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe"
python -m unittest discover -s loopcut/tests -p test_cryptonyan_rig.py -v
python -m unittest discover -s loopcut/tests -p test_cryptonyan_unreal_animation.py -v
```

La seconde suite utilise des doubles d'API ; elle ne lance pas Unreal. Les résultats
cloud sont dans [validation.md](validation.md) ; toutes les tâches PC sont suivies
dans la [checklist centrale](local-pc-checklist.md).

Références API Epic consultées :
[AnimPoseExtensions](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/AnimPoseExtensions?application_version=5.7),
[AnimPoseEvaluationOptions](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/AnimPoseEvaluationOptions?application_version=5.7),
[AnimPoseSpaces](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/AnimPoseSpaces?application_version=5.7),
[AnimDataEvalType](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/AnimDataEvalType?application_version=5.7).
Ces signatures de référence 5.7 doivent être qualifiées dans le moteur cible 5.8.
