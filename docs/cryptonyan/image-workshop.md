# Atelier image → candidat 3D — v0.22

Un agent qui voit une image peut maintenant décrire sa reconstruction dans une
recette JSON, puis exécuter un vrai worker Blender. Celui-ci crée une scène éditable,
un GLB de revue, un rendu CPU et un comparatif HTML autonome avec l'image originale.
Il réutilise les primitives du Creative Kit, Asset Doctor et les contrôles/exporteurs
GLB de Loopcut. Aucun module d'inférence, abonnement ou GPU n'est requis pour les
formes procédurales.

**Ce qui interprète l'image est l'agent, pas ce script.** Le script ne contient pas
de modèle de vision, de photogrammétrie, de reconstruction neuronale ou de recherche
automatique de caméra. Il exécute la recette fournie. Une image unique ne fixe pas
les dimensions réelles ni les faces cachées : ces hypothèses sont obligatoires dans
le plan. Aucun test technique ne certifie une ressemblance artistique.

## Parcours agent et utilisateur

1. Donner l'image à l'agent et préciser l'usage (accessoire, façade, module de niveau),
   une dimension connue et ce qui doit rester fidèle. Convertir la référence en PNG
   RGB/RGBA 8 bits non entrelacé, au plus 4096×4096 et 32 Mio.
2. L'agent examine silhouette, masses, palette, perspective et zones cachées. Il
   écrit une recette à partir de [l'exemple temple](examples/image-workshop-temple.json).
   Cet exemple est un assemblage de démonstration, pas la reconstruction d'une image fournie.
3. Préparer un dossier immuable, puis lancer une tentative dans un autre dossier neuf.
4. Lire `comparison.html` et `asset-doctor.json`, ouvrir `candidate.blend`. Les noms
   des objets correspondent aux IDs de recette. Corriger recette/caméra dans une
   nouvelle préparation pour conserver les versions précédentes.
5. Après revue visuelle, tester le GLB dans une carte de revue Unreal. Cette version
   n'importe pas automatiquement dans le jeu et ne remplace aucun asset existant.

Depuis la racine du fork, sous PowerShell :

```powershell
$env:PYTHONPATH = (Resolve-Path .\scripts\addons_core).Path
py -3.13 -m cryptonyan_asset_studio.image_workshop prepare C:\References\temple.png .\docs\cryptonyan\examples\image-workshop-temple.json --output C:\CryptoNyanWork\temple\reference-001
py -3.13 -m cryptonyan_asset_studio.image_workshop check C:\CryptoNyanWork\temple\reference-001
py -3.13 -m cryptonyan_asset_studio.image_workshop build C:\CryptoNyanWork\temple\reference-001 --blender "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe" --output C:\CryptoNyanWork\temple\attempt-001 --timeout 180
```

Adapter le chemin Blender. Le worker est testé ici sur Blender 4.3.2 Linux ; il
utilise Cycles CPU et ne valide pas CUDA/RTX. La durée maximale est de 600 secondes.
`prepare` et `check` ne lancent pas Blender. `build` crée seulement un candidat local
dans son dossier neuf. Il n'ouvre aucun `.blend` source et ne lance pas de service.

## Recette

Le schéma `cryptonyan.image-workshop/1` contient :

- `id`, `intent`, `assumptions` : identifiant portable, objectif et 1–16 hypothèses ;
- `triangle_budget` : 12–200 000 triangles pour l'ensemble ;
- `camera` : position/cible en mètres Blender Z-up, projection `PERSP` ou `ORTHO`,
  focale, échelle orthographique, résolution 32–1024 par côté, 1–64 samples ;
- `parts` : 1–64 objets, chacun avec `id`, `shape`, `position_m`, `size_m`, `yaw_deg`,
  `color` (RGB linéaire). Formes : `box`, `cylinder`, `cone`, `glb` ;
- `sources` : jusqu'à huit GLB locaux explicitement déclarés, ou `{}`.

`position_m` est le **centre** de la boîte locale, pas le point de contact au sol.
Le yaw tourne autour de Z. Un GLB est recentré et ajusté séparément sur les trois
dimensions de `size_m` : fournir des proportions compatibles pour éviter une
déformation. Sa couleur et ses textures sont conservées ; `color` n'est utilisé
que pour les primitives. Les cylindres/cônes ont 32 segments. Aucun Boolean, découpage
de porte, génération d'intérieur, collision, retopologie, LOD ou rig n'est implicite.

## Recevoir un mesh d'un générateur externe

L'interface actuelle est un **transfert local de GLB**, déjà opérationnel. Elle ne
soumet aucune requête Meshy, Hunyuan, TRELLIS ou SAM 3D. La sélection technique et les
sources sont dans [l'étude des générateurs](image-to-3d-providers.md).

Les workflows TRELLIS déjà présents sur le PC sont prioritaires. Vérifier d'abord
leur fichier de sortie, sans lancer Blender ni toucher au workflow :

```powershell
py -3.13 -m cryptonyan_asset_studio.image_workshop inspect-glb C:\ComfyUI\output\statue.glb
```

Un refus décrit une limite du contrat d'import, pas une mauvaise génération TRELLIS.
La soumission automatique attend un profil adapté aux nœuds réels du workflow.

Dans une recette, remplacer une primitive par :

```json
{
  "id": "Statue", "shape": "glb", "source": "Hero",
  "position_m": [0, 0, 1], "size_m": [1, 1, 2],
  "yaw_deg": 0, "color": [0.5, 0.5, 0.5]
}
```

Et déclarer dans `sources` :

```json
{
  "Hero": {
    "file": "statue.glb",
    "provider": "Nom du fournisseur",
    "model": "Version exacte du modele ou workflow",
    "license": "Identifiant ou reference de licence",
    "reference_sha256": "REMPLACER_PAR_SHA256_DE_L_IMAGE_PNG"
  }
}
```

Calculer le hash avec `Get-FileHash C:\References\temple.png -Algorithm SHA256`,
puis utiliser la valeur en minuscules. Passer `--source-root C:\GeneratedMeshes`
à `prepare` ; les fichiers de `sources` sont relatifs à ce répertoire. Le hash lie
la déclaration à l'image mais **ne prouve pas** que le fournisseur l'a utilisée.
`provider`, `model` et `license` sont des métadonnées déclaratives, sans certification.

Enveloppe volontairement limitée : un nœud, un mesh, un matériau PBR opaque,
transformations appliquées, triangles, pas de rig/animation/morph/hierarchie/extension
glTF. Textures facultatives : PNG intégrés, couleur, metallic-roughness et normale,
selon le contrat PBR existant. Refus des JPEG, URI externes, occlusion séparée,
émission texturée et transparence. Max 32 Mio par GLB et 128 Mio au total.
Le lot est aussi limité à 600 000 sommets et 33 554 432 pixels de textures
décodées, en comptant chaque instance importée (somme des rôles, donc conservative).
Certains exports de générateurs demanderont donc une normalisation préalable dans
Blender. Aucun convertisseur n'efface silencieusement les éléments non pris en charge.

Les [profils ComfyUI de références](comfy-references.md) existants peuvent préparer
des textures depuis la même image. Leur collecteur est PNG/PBR : il ne devient pas
un collecteur GLB simplement en changeant de workflow. L'automatisation ComfyUI
3D (soumission, suivi, récupération GLB et reprise) reste une prochaine étape distincte.

## Résultats et limites

`operation.json` donne `running`, `failed` ou `candidate_created_review_required`,
avec identité du plan et hashes/tailles des artefacts. Un échec conserve les fichiers
partiels pour diagnostic ; ils ne constituent pas une réussite. Relancer dans un
nouveau dossier. Le worker a un timeout et termine son processus enfant à l'arrêt.

| Fichier | Usage |
| --- | --- |
| `candidate.blend` | Scène éditable neuve, images importées empaquetées |
| `candidate.glb` | Géométrie et matériaux de revue, sans caméra ni lumière exportées |
| `render.png` | Vue depuis la caméra déclarée, éclairage fixe documenté |
| `geometry.json` | Triangles, dimensions, caméra, version Blender et avertissements de cadrage |
| `asset-doctor.json` | Audit existant des meshes ; si trop complexes, audit explicitement ignoré et `passed=false` |
| `comparison.html` | Référence et rendu intégrés côte à côte, hypothèses lisibles, sans réseau |

Asset Doctor peut signaler des erreurs sur un candidat : consulter son rapport,
ne pas confondre création du fichier avec approbation de l'asset. Le contrôle de
cadrage porte sur les boîtes englobantes ; il ne vérifie ni occultations ni lisibilité.
Les contrôles GLB comparent nombres de triangles et dimensions ; ils ne prouvent
pas la fidélité de chaque pixel ou shader. Les sources PNG/GLB préparées sont hachées
et recopiées avant l'exécution. Conserver ces dossiers privés, avec un seul écrivain.

Le GLB de scène multi-objets n'est pas un `publication/1` ou `publication/2` du
publisher existant. Pour utiliser ce dernier, publier séparément un objet conforme
depuis `candidate.blend` selon [le guide publisher](publisher.md). Pour Unreal,
vérifier localement import, échelle en centimètres, pivots, UV/matériaux, collisions,
LOD/Nanite et performance avant d'adopter les objets dans CryptoNyanRun.

Les tests utilisent une image synthétique et un tétraèdre créé par le test, pas
une génération neuronale. Ils vérifient de vrais rendus, exports et réouvertures
Blender, pas la qualité d'une reconstruction artistique. Voir la
[checklist PC](local-pc-checklist.md) pour les validations restantes.
