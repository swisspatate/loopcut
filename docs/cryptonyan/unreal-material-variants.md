# Inspecteur Unreal et variantes de matériaux — v0.13

Ce lot raccorde les textures candidates de la [passerelle projet](existing-project.md)
aux **matériaux déjà utilisés par un mesh du jeu**. L'inspection tourne dans Unreal
Python ; la préparation du plan fonctionne hors éditeur. La création dans Unreal
produit de nouvelles textures, une instance de matériau héritée du matériau actuel,
et une copie du mesh portant la variante sur le slot choisi. Les autres slots restent
identiques. Aucun acteur ou niveau existant n'est modifié.

Le code est testé avec des doubles du module Unreal. **Il n'a pas été exécuté ici
dans Unreal 5.8.3** : les API, les shaders, la sauvegarde/relecture et l'apparence
doivent être vérifiés sur le PC. Les tests Blender de l'extension ne remplacent pas
cette validation. Le plugin de démonstration `CryptoNyanRuntime` n'est pas requis.

Depuis la v0.21, un parcours distinct permet d'[appliquer et restaurer ces MIC sur
les composants d'un niveau existant](level-material-review.md). Il conserve les
overrides d'origine et vérifie les conflits ; la création de variantes décrite ici
reste indépendante de l'affectation aux acteurs.

## 1. Inspecter un asset enregistré dans Unreal

Ouvrir le projet existant avec Python Editor Script et les API d'édition d'assets
disponibles. Attendre la fin du chargement de l'Asset Registry. Sauvegarder ou écarter
les modifications des sources avant de préparer une variante. Un seul éditeur/agent
doit écrire dans ce projet pendant l'opération.

Dans la console Python d'Unreal, adapter les chemins et le véritable chemin d'objet
obtenu dans le Content Browser (sans l'enveloppe `StaticMesh'...'`) :

```python
import sys
from pathlib import Path
sys.path.insert(0, r"C:\src\loopcut\scripts\addons_core")
from cryptonyan_asset_studio.unreal_material_variants import inspect_asset, create_variant
inspection_dir = Path(r"C:\CryptoNyanJobs\existing-game\textures\inspections")
inspection_dir.mkdir(parents=True, exist_ok=True)
inspection = inspect_asset(
    "/Game/Props/SM_Lantern.SM_Lantern",
    inspection_dir / "lantern-001.json",
)
print(inspection["slots"])
```

Le rapport contient :

- classe réellement retournée par l'éditeur, slots de matériaux et leurs noms ;
- chaîne des matériaux parents, paramètres texture/scalaires/vectoriels effectifs ;
- références et réglages des textures 2D, référence au squelette des Skeletal Meshes ;
- dépendances et référents **directs** de package, lus dans l'Asset Registry ;
- empreintes des `.uasset` inspectés et de leurs éventuels `.uexp`/`.ubulk` ;
- packages concernés ayant des modifications non sauvegardées.

Ce rapport ne valide pas le skinning ou les animations. Il ne parcourt pas les
graphes de textures non paramétrées ni la fermeture transitive des dépendances.
Les références aux packages Engine/plugins sont indiquées sans hacher leurs fichiers.
Les overrides de matériaux placés sur les acteurs/composants du niveau sont hors
périmètre : l'inspection porte sur l'asset du Content Browser.

Les rapports sont créés exclusivement hors du projet ; un nom existant est refusé.
Ils contiennent des chemins et noms privés : les conserver dans le workspace local,
pas dans le dépôt public d'outillage.

## 2. Générer et collecter une texture liée au même asset

Utiliser `project_texture_submit`, puis `texture_status` et
`project_texture_collect` comme décrit dans le guide projet. La cible doit être le
fichier `Content/.../*.uasset` correspondant exactement au mesh inspecté.
Une texture associée à un `.blend` ne sera pas automatiquement transférée sur un
`.uasset` : leur correspondance demande un adaptateur d'export distinct.

La chaîne ComfyUI garde ses profils configurables et ses modèles locaux. Une image
générée n'est pas une preuve de compatibilité avec les UV, un atlas ou la direction
artistique du jeu. Plusieurs variantes utilisent des identifiants de demande distincts.

## 3. Préparer le plan avec l'agent

Le serveur configuré avec `--game-project` et `--comfy-profiles` expose désormais
`project_material_plan`. Exemple fictif, **à remplacer par les paramètres observés** :

```json
{
  "request_id":"garden-lantern-paper-001",
  "inspection":"lantern-001.json",
  "slot":0,
  "bindings":{"base_color":"PaperColor"},
  "variant_id":"GardenLanternRed001"
}
```

`inspection` est relatif au sous-dossier `textures/inspections` du workspace.
Le service vérifie que le candidat, le projet et l'inspection correspondent à la
demande détenue. Il renvoie le fichier du plan et sa destination :
`/Game/CryptoNyan/MaterialVariants/GardenLanternRed001`.
Une réutilisation du même identifiant avec d'autres paramètres est refusée.
Cette étape ne lance pas Unreal et ne modifie pas le projet.

Chaque canal du bundle doit avoir un paramètre de texture explicite, distinct et
présent dans l'inspection. Par exemple, un bundle contenant base color et normale
exige deux bindings. L'outil ne devine pas qu'un paramètre nommé `Mask` doit recevoir
de la rugosité, et ne remplace pas une texture de graphe non paramétrée.

Alternative sans agent, depuis PowerShell avec `PYTHONPATH` configuré :

```powershell
py -3.13 -m cryptonyan_asset_studio.unreal_material_variants plan `
  --inspection 'C:\CryptoNyanJobs\existing-game\textures\inspections\lantern-001.json' `
  --candidate 'C:\CryptoNyanJobs\existing-game\textures\asset-bindings\garden-lantern-paper-001.candidate.json' `
  --slot 0 --bindings 'C:\CryptoNyanJobs\bindings.json' `
  --destination '/Game/CryptoNyan/MaterialVariants/GardenLanternRed001' `
  --report 'C:\CryptoNyanJobs\lantern-plan.json'
```

`bindings.json` contient par exemple `{"base_color":"PaperColor"}`. Le fichier
de sortie doit être nouveau et hors du jeu et du bundle de textures.

## 4. Créer une variante dans Unreal

Dans la même console Python d'Unreal, utiliser le chemin de plan retourné :

```python
result = create_variant(
    r"C:\CryptoNyanJobs\existing-game\textures\asset-bindings\garden-lantern-paper-001.GardenLanternRed001.plan.json",
    r"C:\CryptoNyanJobs\lantern-import-001.json",
    apply=True,
)
print(result["status"])
print(result.get("preview_mesh"))
```

Sans `apply=True`, l'opération est un dry-run : les reçus et textures sont vérifiés,
mais Unreal n'est pas importé et aucun asset n'est créé. Ce dry-run fonctionne aussi
avec `python -m cryptonyan_asset_studio.unreal_material_variants create PLAN --report RAPPORT`.
La création effective doit être appelée dans Unreal Python, éventuellement via les
outils Python découverts par le client MCP local déjà présent dans le jeu. Aucun nom
de toolset MCP natif n'est supposé ni activé automatiquement par cette extension.

Avant de créer, l'outil réinspecte le mesh et compare le résultat au plan. Il refuse
les modifications de fichier, de parent, de paramètres, de slots, de squelette ou les
packages concernés devenus dirty. Il réitère ces contrôles pendant l'opération.
Le dossier de destination doit être inexistant ; les imports ne remplacent rien.

Les nouveaux assets sont :

- `T_base_color` et les éventuels `T_roughness`, `T_metallic`, `T_normal` ;
- `MI_Variant`, dont le parent est le matériau actuellement affecté au slot, même
  si celui-ci est déjà une instance avec ses propres réglages ;
- `SM_Preview` ou `SK_Preview`, copie du mesh, avec un seul slot remplacé.

Les paramètres non remplacés sont relus pour vérifier leur héritage. Les slots de la
copie sont contrôlés ; une copie Skeletal Mesh doit garder le même objet Skeleton.
La géométrie, les collisions, les animations et les rigs ne sont pas retravaillés par
l'outil. Leur transport par duplication et leur comportement restent à valider dans
l'éditeur réel ; la référence identique au squelette ne certifie pas les déformations.

Seuls les nouveaux assets sont sauvegardés. Le résultat attendu est
`created_review_required`, jamais une approbation artistique ou une promotion dans
les niveaux. Ouvrir `preview_mesh` dans l'éditeur de mesh pour comparer. Pour une
comparaison en scène, placer cette copie dans une map de revue séparée. L'application
aux acteurs existants, les captures automatiques appariées et le retour arrière
d'une affectation en niveau restent à développer.

## Conventions et limites

- Base color : sRGB, compression par défaut. Rugosité/métallique : linéaire,
  compression Masks. Les bindings supposent des canaux séparés ; pas de packing ORM.
- Les normales Material Doctor sont OpenGL +Y. L'import Unreal met explicitement
  `flip_green_channel=True`, compression Normalmap et sRGB désactivé, sans modifier
  le PNG. **Une seule conversion** ; ne pas fournir un PNG déjà converti DirectX.
- Normales acceptées seulement si le matériau de base utilise l'espace tangent.
  Le sens visuel des reliefs et le type de sampler doivent être vérifiés localement.
- Première version limitée aux paramètres avec une texture 2D existante non virtuelle.
  Paramètres sans valeur, textures virtuelles, instances dynamiques, matériaux avec
  `use_material_attributes`, couches et noms ambigus exigent un adaptateur distinct.
- Maximum 32 slots, 16 niveaux de parents, 64 matériaux, 256 textures et 64 paramètres
  par catégorie/matériau ; 2 048 dépendances et référents directs chacun. Lecture de
  fichiers limitée à 512 Mio par package et 1 Gio distinct au total par inspection.
- Les PNG sont copiés à côté du reçu dans un dossier `nom-du-reçu-inputs`, conservé
  pour les futures réimportations Unreal. Ne pas le supprimer après création.
- Une erreur conserve les créations partielles, les snapshots et le reçu avec les
  assets explicitement sauvegardés. Aucun nettoyage automatique. Une nouvelle tentative
  utilise un nouvel identifiant après examen du dossier partiel.

## Validation locale requise

Suivre [la checklist](local-pc-checklist.md#0bis-inspecteur-et-variantes-unreal-v013) :
un mesh statique à plusieurs slots, un mesh animé existant, une texture de normales
asymétrique, réouverture après sauvegarde, shaders et comparaison visuelle. Commencer
dans une copie de test du projet. Ne pas confondre succès du reçu et qualité du rendu.
