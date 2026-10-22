# Niveaux modulaires à contraintes — v0.28

Composer des salles et couloirs à partir de modules réutilisables : trajet principal,
points de passage obligatoires, embranchements, boucles et pièces à thème. La seed
fixe les choix. Les sources GLB sont copiées et vérifiées ; un aperçu Blender et une
recette pour le Creative Director Unreal réutilisent le même placement.

Le système complète les kits de runner existants par un graphe sur grille plane.
Il n'analyse pas automatiquement un `.umap` pour en déduire les salles. Si le
contrôleur impose une course dans une seule direction, les virages de ce graphe
nécessitent un comportement de déplacement adapté et un essai en jeu.

## Essayer sans préparer d'assets

Le générateur de démonstration réutilise les helpers de géométrie/matériaux et
l'exporteur GLB de Loopcut. Il crée cinq meshes : extrémité, couloir droit, angle,
jonction en T et croisement. Les sols, murs, portes centrées et proxies de murs
sont définis explicitement. Aucun modèle IA ni dépôt supplémentaire à installer.

Depuis la racine du fork, dans PowerShell :

```powershell
$env:PYTHONPATH = "$PWD\scripts\addons_core"
$modularWork = 'D:\CryptoNyanWork\Modular'
New-Item -ItemType Directory -Force $modularWork | Out-Null
$modularBlender = 'D:\Dev\loopcut\blender.exe'
python -m cryptonyan_asset_studio.modular_levels demo --output "$modularWork\sources" --blender $modularBlender
python -m cryptonyan_asset_studio.modular_levels prepare "$modularWork\sources\recipe.json" --catalog "$modularWork\sources\catalog.json" --source-root "$modularWork\sources" --output "$modularWork\level-01"
python -m cryptonyan_asset_studio.modular_levels check "$modularWork\level-01"
python -m cryptonyan_asset_studio.modular_levels preview "$modularWork\level-01" --output "$modularWork\preview-01" --blender $modularBlender
```

Renseigner le véritable exécutable Blender. Chaque dossier de sortie doit être
nouveau. Ouvrir `preview-01/modular-preview.blend` pour examiner les meshes
instanciés, les repères Start/Goal/checkpoints et les connexions représentées par
une courbe de revue. Cette courbe n'est pas un NavMesh.

Le panneau **Vue 3D → CryptoNyan → Niveaux modulaires à contraintes** propose
préparation, vérification et aperçu isolé. Les calculs sont synchrones. La scène
ouverte au lancement n'est pas remplacée par le fichier d'aperçu.

## Modifier le parcours

Exemple complet : [examples/modular-level.json](examples/modular-level.json).
Le kit de démonstration en écrit aussi une copie `recipe.json`.

- `grid` et `blocked` : taille de la grille et cellules interdites.
- `start`, `goal` : cellules de départ et d'arrivée.
- `waypoints` : points à visiter dans l'ordre, avec un tag de module facultatif.
  Le solveur interdit les boucles qui permettraient de contourner un checkpoint.
- `route_cells: [minimum, maximum]` : longueur du trajet principal en modules.
- `branches` : nombre, longueur et tag requis au bout des embranchements ; par
  exemple `Reward` pour réserver une pièce où placer ensuite une récompense.
- `loops` : nombre exact de connexions supplémentaires. Une demande impossible
  sous les contraintes produit un échec explicite.
- `required_tags` : tags nécessaires pour tous les modules ; les tags de checkpoints
  et fins de branches ajoutent des contraintes locales. Les tags sont sensibles à la casse.
- `player` : rayon, hauteur et marge utilisés pour les portes et les proxies de
  dégagement. Les adapter à la vraie capsule du jeu.
- `anchor_m` : origine du niveau, en mètres dans le repère Unreal.
- `seed` et `search_budget` : choix déterministes et budget borné de recherche.
- `destination`, `target_level` : nouveau dossier et carte de revue pour l'adaptateur
  Unreal existant ; voir la section suivante.

Les embranchements et checkpoints sont des indications de structure. Cette version
n'ajoute pas de Blueprint de récompense, de trigger ni de logique de sauvegarde.

Le bundle contient `plan.json`, `geometry.json`, `overview.svg`, `level-points.csv`,
les GLB figés sous `sources`, et `director.json` si tous les modules utilisés sont
mappés vers des assets Unreal. Le CSV contient des coordonnées Unreal en centimètres
et des yaw en degrés ; c'est un échange de points neutre, pas un asset PCG/HISM natif.

## Réutiliser tes propres modules

Partir du catalogue de démonstration, remplacer les fichiers GLB et adapter les
portes/proxies. Un catalogue `cryptonyan.modular-catalog/1` possède `cell_m` et
une liste de modules avec :

| Champ | Signification |
| --- | --- |
| `id` | Identifiant unique du module. |
| `preview_glb` | Chemin relatif et SHA-256 du GLB exporté. |
| `unreal_mesh` | Chemin du StaticMesh existant `/Game/...Asset.Asset`, ou `null` pour l'aperçu seul. |
| `tags` | Tags utilisés pour les contraintes de thème/type de pièce. |
| `doors` | Côtés locaux `east`, `north`, `west`, `south`, type de connecteur, largeur et hauteur. |
| `blockers_m` | Boîtes solides déclarées, `min`/`max`, servant au contrôle conservateur de dégagement. |

Une cellule est centrée sur l'origine du module, le sol de circulation à Z=0.
Les coordonnées du catalogue sont des **mètres Unreal** : east = +X, north = +Y.
Pour les meshes Blender : X = X Unreal, Y = −Y Unreal, Z = Z Unreal. Les portes
sont centrées sur les faces de la cellule, sans décalage latéral ou marche verticale.
Leurs types doivent correspondre de part et d'autre. La largeur et la hauteur
utilisables sont les minima des deux ouvertures.

Le GLB doit respecter le contrat statique existant de l'Image Workshop : un mesh,
un node, un matériau opaque compatible, transformations baked, textures PNG
embarquées et aucun rig/animation/ressource externe. Exporter un module de décor,
pas le personnage riggé ni un niveau complet. Le mesh doit tenir dans sa cellule,
inclure le plan Z=0 dans ses bornes, et atteindre le bord correspondant à chaque
porte déclarée. Les limites sont vérifiées sur les positions binaires réelles des
vertices ; des min/max d'accessor incorrects sont refusés.

Les rotations sont des quarts de tour. Le catalogue doit couvrir les formes de
portes nécessaires : extrémités, lignes, angles, jonctions, etc. Les murs/détails
intérieurs restent ceux de tes assets, et les proxies doivent réellement décrire
leurs obstacles à hauteur du joueur. Une vérification de proxy ne mesure pas une
ouverture directement dans le mesh.

Après modification d'un GLB, actualiser son SHA-256 :

```powershell
(Get-FileHash 'D:\CryptoNyanWork\Modular\sources\Straight.glb' -Algorithm SHA256).Hash.ToLowerInvariant()
```

Préparer ensuite un nouveau bundle ; les précédents restent liés à leurs sources
copiées. Pour une variante visuelle, changer les modules/tags et la seed ; les
matériaux PBR embarqués sont importés et packed dans l'aperçu Blender.

## Revue dans Unreal 5.8

La démonstration laisse `unreal_mesh` à `null` : elle ne crée ni n'importe d'assets
Unreal. Pour tes assets déjà importés, renseigner leurs chemins réels dans le
catalogue puis préparer un nouveau bundle. Le `.uasset` doit correspondre au GLB,
avec le même pivot et les mêmes bornes locales.

Créer et ouvrir une **carte de revue vide et enregistrée** correspondant au
`target_level` de la recette. Elle doit contenir seulement WorldSettings. Enregistrer
les changements de contenu avant le test. Choisir un nouveau `destination` sous
`/Game/CryptoNyan/DirectedReviews/` pour chaque placement conservé.

Dans la console Python de l'éditeur Unreal :

```python
import sys
sys.path.insert(0, r"D:\Dev\loopcut\scripts\addons_core")
from cryptonyan_asset_studio.unreal_modular import review
review(r"D:\CryptoNyanWork\Modular\level-ue-01", r"D:\CryptoNyanWork\Modular\ue-check-01")
# Examiner le dry-run et ses reçus, puis lancer explicitement :
review(r"D:\CryptoNyanWork\Modular\level-ue-01", r"D:\CryptoNyanWork\Modular\ue-apply-01", apply=True)
```

Le raccord vérifie la version d'éditeur, les classes StaticMesh et les bornes locales
par rapport aux GLB (tolérance 1 mm), puis délègue au Creative Director existant.
Celui-ci lie les fichiers du projet par hash, vérifie la carte vide, place les
acteurs et contrôle leurs transformations ; il conserve ses règles de restauration
en cas d'échec. Il ne sauvegarde pas la carte. Les reçus détaillés restent dans le
nouveau dossier de travail. Une erreur après l'appel doit aussi être examinée dans
`director-receipt.json`, qui indique les acteurs éventuellement créés/retirés.

Des bornes identiques ne prouvent pas que la géométrie, les matériaux ou les profils
de collision sont identiques. Vérifier les collisions et le NavMesh dans l'éditeur,
puis faire parcourir le niveau au vrai personnage avant adoption dans le jeu.

## Garanties et limites du modèle

- Grille plane jusqu'à 12×12 cellules ; 64 modules placés au maximum, 6 checkpoints,
  4 branches et 8 boucles. 32 définitions de modules, 128 Mio de sources, 2 millions
  de vertices source et 2 millions de triangles instanciés maximum.
- Trajet principal simple, branches hors cellules occupées, graphe connecté et
  checkpoints dont le retrait coupe la connexion start→goal. Les voisins non
  reliés doivent avoir leurs côtés fermés selon le catalogue.
- Contrôle des portes déclarées, dégagement conservateur du centre vers chaque
  porte via une empreinte carrée élargie du joueur, et absence de chevauchement
  volumique des bornes de modules. Les proxies entièrement sous le sol ou au-dessus
  du joueur ne bloquent pas le passage.
- Le solveur choisit d'abord une topologie puis affecte des modules. Son échec borné
  ne prouve pas qu'aucun autre niveau satisfaisant n'existe. Modifier seed, cellules,
  longueur, tags, bibliothèque ou budget plutôt que contourner les validations.
- Une cellule/passage déclaré n'est pas une simulation du contrôleur, des sauts,
  de la physique ou du NavMesh. Les flags de qualification moteur restent faux.
- Les ports verticaux/escaliers entre étages, placement sur terrain par raycast,
  PCG/HISM natif, portes dynamiques et validation automatique des parcours en jeu
  restent à développer.

Qualification des vrais modules et d'Unreal : [checklist PC](local-pc-checklist.md).
