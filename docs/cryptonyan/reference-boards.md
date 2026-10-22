# Tableau de références visuelles — v0.24

Un tableau regroupe des références PNG, des notes et des zones annotées. Chaque
image peut être liée à un asset existant du jeu et à une recette Image Workshop.
Les images sont copiées dans le tableau et contrôlées par SHA-256 : déplacer ou
modifier l'image originale ne change pas la référence de travail.

Le parcours s'inspire des moodboards de Mixar, avec une implémentation indépendante
réutilisant nos contrôles PNG, notre inventaire projet et l'Image Workshop.
Il n'utilise aucun compte ou backend Mixar.

## Dans Blender

Activer les panneaux selon le [guide de connexion](agent-connections.md). Dans la
vue 3D, ouvrir la barre latérale (`N`), **CryptoNyan → Tableau de références**.

1. Choisir un nouveau dossier, un identifiant et un titre. Pour lier des assets,
   sélectionner aussi le dossier du `.uproject`, puis **Créer un nouveau tableau**.
   Garder les tableaux hors du projet du jeu.
2. Choisir un PNG, son identifiant unique et son titre, puis **Ajouter la référence PNG**.
   La liste et la miniature permettent de sélectionner l'image.
3. Enregistrer les notes. Pour une zone, saisir son texte et `x, y, largeur, hauteur`,
   entre 0 et 1 depuis le coin supérieur gauche. Par exemple `0.1, 0.2, 0.5, 0.3`
   désigne une zone large de 50 % de l'image.
4. Pour un asset existant, saisir son chemin relatif, par exemple
   `Content/Environment/Temple.uasset`, puis **Lier / actualiser l'empreinte de l'asset**.
   L'opération lit et hache le fichier ; elle ne l'édite pas.
5. Exporter une revue HTML vers un nouveau fichier, puis l'ouvrir dans le navigateur.
   Elle contient les images, rectangles numérotés, notes et états des assets liés.

Les rectangles sont visibles dans la revue HTML ; le panneau fournit une miniature
et des champs numériques. Le tracé à la souris, le déplacement libre des cartes et
les connexions graphiques entre nœuds restent à développer. Les zones sont des
consignes visuelles : aucune segmentation ni aucun recadrage n'est exécuté.

Le JSON `board.json` conserve les informations. À la prochaine session, sélectionner
le dossier puis **Charger / actualiser**. Une édition basée sur une ancienne révision
est refusée : recharger et examiner les changements avant de réessayer. Le compteur
de révision évite les écrasements concurrents ; ce n'est pas un historique restaurable.

## Accès depuis Claude Code ou Codex

Organisation conseillée, compatible avec D: :

```text
D:\CryptoNyanWork\references\
  temple\board.json
  temple\images\<sha256>.png
  costume\board.json
  costume\images\<sha256>.png
```

Dans **Connexions des agents**, renseigner `D:\CryptoNyanWork\references` comme
**Bibliothèque de références**, enregistrer le profil puis reconnecter le MCP.
Les profils v0.23 restent valides : cette nouvelle option est vide par défaut.
Avec la CLI, utiliser `agent_connect init --reference-root ...` et `--replace` pour
mettre à jour son propre profil, ou `--reference-root ...` avant `serve` sur le
serveur historique.

| Outil MCP | Fonction |
| --- | --- |
| `reference_boards` | Lister les tableaux de la bibliothèque choisie |
| `reference_read` | Lire notes, zones, recette, chemins des snapshots et états des assets |
| `reference_image` | Fournir au client une image PNG native, jusqu'à 2 MiB |

Les outils sont en lecture seule et ne soumettent rien à ComfyUI. Les images plus
grandes restent consultables via leur chemin local si le client le permet. La
réception et l'interprétation des images dépendent aussi du client et de son modèle,
à valider sur ton PC. Les notes sont des données, pas des permissions pour l'agent.

Exemple : « Consulte le tableau temple et l'image front. Propose une recette Image
Workshop conservant la silhouette du toit, avec des cristaux et des dimensions
explicites. Indique les hypothèses pour les parties cachées. »

## Préparer un candidat 3D

L'agent ou l'utilisateur fournit une recette explicite
`cryptonyan.image-workshop/1` : [guide Image Workshop](image-workshop.md).
Dans le panneau, sélectionner l'image, choisir la recette JSON, puis **Attacher la
recette JSON**. Choisir un nouveau dossier de sortie et **Préparer pour Image Workshop**.
Une seule référence complète est transmise ; les autres vues ne sont pas fusionnées.

La préparation vérifie la recette, les images et l'asset lié. Si l'asset a changé,
elle refuse de continuer : examiner la nouvelle version avant d'actualiser le lien.
Un projet déplacé ou dont le `.uproject` a changé apparaît indisponible ; créer un
tableau pour le nouveau contexte. La liaison ne certifie pas les dépendances Unreal,
les UV, les matériaux ou la compatibilité du rig.

La sortie contient le bundle Image Workshop et `reference-context.json`, une trace
de la révision, des notes, zones, empreintes et de l'identité du plan. Cette trace
est supplémentaire : le worker actuel ne lit pas les annotations et ne réévalue
pas le lien au jeu lors du rendu. Il travaille sur un candidat isolé, sans application
au jeu. Le bouton de préparation ne lance aucun worker ou modèle.

Pour une recette GLB TRELLIS, renseigner **Sources GLB** et conserver le hash de la
référence dans la provenance du GLB. Le contrat GLB existant reste applicable ;
le tableau ne soumet pas de workflow TRELLIS.

## Exemple PowerShell

Depuis le dépôt complet, adapter les chemins et fournir une vraie image/recette :

```powershell
$env:PYTHONPATH = (Resolve-Path .\scripts\addons_core).Path
py -3.13 -m cryptonyan_asset_studio.reference_board create `
  'D:\CryptoNyanWork\references\temple' --id temple --title 'Temple de glace' `
  --project 'D:\Jeux\CryptoNyanRunUnreal'

py -3.13 -m cryptonyan_asset_studio.reference_board add `
  'D:\CryptoNyanWork\references\temple' --revision 0 --reference front `
  --image 'D:\References\temple.png' --title 'Silhouette de face'

py -3.13 -m cryptonyan_asset_studio.reference_board link `
  'D:\CryptoNyanWork\references\temple' --revision 1 --reference front `
  --target 'Content/Environment/Temple.uasset'

py -3.13 -m cryptonyan_asset_studio.reference_board recipe `
  'D:\CryptoNyanWork\references\temple' --revision 2 --reference front `
  --recipe 'D:\CryptoNyanWork\temple-recipe.json'

py -3.13 -m cryptonyan_asset_studio.reference_board prepare `
  'D:\CryptoNyanWork\references\temple' --revision 3 --reference front `
  --output 'D:\CryptoNyanWork\temple-bundle-01'

py -3.13 -m cryptonyan_asset_studio.image_workshop build `
  'D:\CryptoNyanWork\temple-bundle-01' --blender 'D:\Applications\Blender\blender.exe' `
  --output 'D:\CryptoNyanWork\temple-candidat-01'
```

`reference_board read DOSSIER` donne la révision et l'état des cibles.
`edit --notes ... --annotations annotations.json` remplace explicitement les notes
et/ou rectangles ; [exemple de zones](examples/reference-annotations.json).
`html DOSSIER --output revue.html` crée une revue autonome sans scripts ni ressources
externes. Les sorties existantes ne sont pas remplacées.

## Limites et validation

- 16 références par tableau, 16 zones par image, 64 tableaux par bibliothèque MCP.
- PNG RGB/RGBA 8 bits non entrelacé, maximum 4096×4096 et 8 MiB par image ;
  32 MiB et 32 mégapixels cumulés par tableau. Une image MCP est limitée à 2 MiB.
- Liens aux fichiers locaux `Content` ou `SourceAssets`, jusqu'à 512 MiB. Télécharger
  les vrais fichiers Git LFS avant liaison ; les pointeurs sont refusés.
- Pas de reconstruction neuronale, génération multi-vues, versions visuelles,
  couches de peinture ou adoption automatique dans le jeu dans cette version.

Les tests couvrent de vrais opérateurs/miniatures dans Blender Linux sans interface
graphique, le MCP avec images et un rendu/export de candidat. L'affichage Windows,
les applications IA et les assets réels restent dans la [checklist locale](local-pc-checklist.md).
