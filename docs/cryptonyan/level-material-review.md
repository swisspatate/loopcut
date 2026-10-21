# Tester une variante dans un niveau existant et revenir en arrière — v0.21

Cette extension applique des **MaterialInstanceConstant déjà créées et sauvegardées**
aux composants sélectionnés d'un niveau existant. Elle complète les
[variantes de matériaux](unreal-material-variants.md), les
[collections ComfyUI](texture-collections.md) et les
[tenues](rich-levels-and-wardrobe.md).

Le parcours est : **inspecter la sélection → préparer un plan → lire le comparatif
→ appliquer dans Unreal → conserver ou restaurer**. Le niveau ouvert est modifié
en mémoire lors de l'application. L'outil ne sauvegarde ni carte, ni mesh, ni matériau.
Il n'exige pas une carte de revue vide et ne change pas la sélection ou la caméra.

Le comparatif HTML montre les affectations avant/après, pas des images rendues.
Pour juger l'apparence, comparer dans le même viewport après application/restauration,
ou réaliser des captures manuelles avec caméra, éclairage, exposition et frame identiques.
Il n'y a pas de score artistique ni de capture automatique dans cette version.

## 1. Inspecter les objets sélectionnés dans Unreal 5.8

Activer Python Editor Script et Editor Scripting Utilities. Le plugin de démonstration
CryptoNyanRuntime n'est pas requis. Arrêter PIE, attendre le chargement du niveau,
sauvegarder les modifications des cartes et assets, puis sélectionner les acteurs
concernés dans l'Outliner. Les fichiers Git LFS doivent être téléchargés.

Dans la console Python, adapter les chemins locaux :

```python
import sys
from pathlib import Path
sys.path.insert(0, r"C:\Dev\loopcut\scripts\addons_core")
from cryptonyan_asset_studio.unreal_level_materials import inspect_selection, execute, restore
work = Path(r"C:\CryptoNyanWork\level-review")
work.mkdir(parents=True, exist_ok=True)
capture = inspect_selection(work / "selection-001.json")
for row in capture["components"]:
    print(row["component"], list(enumerate(row["slot_names"])), row["effective"])
```

Le rapport contient le chemin et le GUID de l'acteur, le chemin du composant,
sa classe, le mesh, les noms de slots, les matériaux hérités, les overrides exacts,
les matériaux effectifs et les hashes des assets explicites. Il garde la différence
entre un slot hérité et un override qui pointe vers le même matériau.

Périmètre de cette version :

- 1–32 acteurs sélectionnés, au plus 32 composants et 32 slots par composant ;
- `StaticMeshComponent` et `SkeletalMeshComponent` natifs ou ajoutés comme instances ;
- composants directs d'acteurs chargés du niveau persistant, avec GUID non nul ;
- meshes et matériaux sauvegardés sous `/Game`, avec noms de chemins portables ;
- refus des matériaux dynamiques, ISM/HISM/foliage, composants issus d'un Construction
  Script, packages d’acteurs externes (dont World Partition), niveaux streamés et objets de PIE. Un composant non pris en charge dans
  la sélection bloque l'inspection entière plutôt que d'être ignoré silencieusement.

Un Mesh natif d'un Blueprint Character peut être inspecté, mais cette opération
ne modifie pas ses valeurs par défaut de classe. Les changements qu'un Blueprint,
Construction Script ou système de skin ferait ensuite ne sont pas neutralisés.
Qualifier ce parcours localement avant de l'utiliser sur le héros du jeu.

## 2. Préparer le plan hors éditeur

Copier [level-material-assignments.json](examples/level-material-assignments.json)
et remplacer les chemins fictifs par ceux du rapport. Chaque ligne donne exactement
`component`, `slot` (indice entier commençant à zéro) et `material` (chemin du MIC
candidat). Au plus 128 affectations, sans doublon composant/slot. Les opérations
qui ne changeraient pas le matériau effectif sont refusées.

```powershell
$env:PYTHONPATH = (Resolve-Path .\scripts\addons_core).Path
py -3.13 -m cryptonyan_asset_studio.level_materials C:\CryptoNyanWork\level-review\selection-001.json C:\CryptoNyanWork\level-review\assignments.json --output C:\CryptoNyanWork\level-review\plan-001.json --html C:\CryptoNyanWork\level-review\comparison-001.html
```

Le plan fixe les composants et slots précis, les états avant/après, l'identité du
projet et les hashes des meshes/MIC/matériaux explicitement référencés ainsi que
leurs `.uexp`/`.ubulk`. La carte doit correspondre à celle capturée avant application.
La fermeture transitive des textures et graphes de matériaux n'est pas hachée :
ces contrôles protègent les affectations, pas toute l'apparence du rendu.

Le HTML est autonome, sans requête réseau, et échappe les noms issus du projet.
Les rapports peuvent contenir des noms privés du jeu : les conserver localement.

## 3. Appliquer et comparer

Une simulation de plan ne charge pas Unreal et ne modifie aucun composant :

```powershell
py -3.13 -m cryptonyan_asset_studio.unreal_level_materials apply C:\CryptoNyanWork\level-review\plan-001.json --output C:\CryptoNyanWork\level-review\dry-001
```

Dans la console Python d'Unreal, toujours sur le même niveau :

```python
result = execute(work / "plan-001.json", work / "apply-001", apply=True)
print(result)
```

Le résultat attendu est `applied_review_required`. Avant le premier changement,
le code vérifie tous les composants ciblés : GUID, classe, mesh, noms des slots,
overrides et matériaux effectifs. Une modification entre la capture et l'application
bloque le lot entier. Il revérifie chaque composant juste avant son écriture et
relit les overrides/matériaux après. Chaque changement s'inscrit dans une transaction
éditeur, puis dans un reçu durable. Les acteurs non ciblés restent hors mutation.

Examiner visuellement les matériaux. Si la variante convient, sauvegarder la carte
manuellement avec ton flux habituel de versionnement. Le journal ne remplace pas Git,
les sauvegardes ni les opérations de contrôle de versions de l'éditeur.

## 4. Restaurer les matériaux d'origine

Le dossier `apply-001` contient `plan.json` et `operation.json`. Le conserver entier.
Chaque intention est écrite **avant** de changer un composant. Le journal permet de
reprendre une application interrompue sans supposer que tous les changements ont réussi.

```python
result = restore(work / "apply-001", work / "restore-001", apply=True)
print(result)
```

La restauration vérifie tous les composants dont la modification a été tentée.
Elle ne touche que ceux qui correspondent exactement à l'état candidat connu.
Ceux déjà revenus à l'original sont signalés dans `already_original`, sans écriture.
Un slot modifié entre-temps, un autre mesh, un acteur recréé avec le même nom, une
source changée ou un composant absent provoquent un refus. Les modifications sans
rapport, comme le déplacement d'un acteur, sont conservées.

Les listes d'overrides sont restaurées **à l'identique**, y compris une liste vide
ou des entrées nulles : les slots hérités continuent donc d'hériter du mesh. Copier
simplement les matériaux effectifs dans tous les slots aurait cassé cet héritage.

Le niveau peut avoir été sauvegardé depuis l'application. La restauration n'impose
pas son ancien hash `.umap` ; elle exige le même projet, la même carte, les mêmes
GUID et les états ciblés attendus. Elle ne restaure pas tout le fichier de carte.
Après restauration, sauvegarder la carte manuellement si le retour doit persister.
Le comportement après sauvegarde/réouverture doit être validé sur le PC. Les
acteurs externes World Partition exigent un adaptateur distinct : leurs packages
sont refusés avant mutation, et aucune cellule n’est chargée automatiquement.

## 5. Échecs et reprise

| Situation | Comportement |
| --- | --- |
| Échec avant mutation | Reçu `failed`, aucune intention de changement enregistrée |
| Échec partiel d'application | Retour conditionnel aux états originaux des composants tentés ; les états inattendus restent intacts et figurent dans `conflicts` |
| Interruption brutale | À la relance, examiner le journal puis appeler explicitement `restore` ; aucune reprise automatique |
| Conflit avant restauration | Aucun composant du lot n'est restauré ; examiner les modifications concurrentes |
| Échec pendant restauration | Les composants déjà restaurés restent originaux ; relancer depuis le journal d'application, avec un nouveau dossier de résultat |
| Seconde restauration | Les états déjà originaux sont constatés sans réécriture |

Toutes les sorties doivent être neuves et hors du projet. Ne pas modifier les plans
ou journaux pour contourner un refus. Un seul éditeur/agent doit écrire sur les
composants concernés ; comparer les valeurs ne permet pas de distinguer deux éditions
successives strictement identiques. Éviter les revues imbriquées sur les mêmes composants.

Tests disponibles :

```powershell
py -3.13 -m unittest discover -s loopcut/tests -p test_cryptonyan_level_materials.py -v
```

Les tests sont des doubles stricts des API Unreal et des tests de fichiers/CLI.
Ils ne valident pas le moteur : affichage du matériau, notifications d'édition,
Undo/Redo, sauvegarde/réouverture, Blueprints et comportement du vrai niveau restent
à qualifier dans la [checklist PC](local-pc-checklist.md).
