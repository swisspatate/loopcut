# Ajuster un vêtement au rig existant — v0.20

`garment_fit` ajuste **un vêtement déjà modélisé et aligné** près du corps,
transfère ses poids, exporte des masques d'occupation UV et mesure les intersections
sur une action choisie. Il produit `candidate.blend` dans un nouveau dossier ;
le `.blend` original n'est pas sauvegardé ni modifié.

Prérequis : scène autonome avec ressources empaquetées, corps fermé avec normales
cohérentes vers l'extérieur (ou proxy pondéré équivalent), un seul modificateur
Armature sur le corps, rig en mode Pose. Vêtement statique sans parent, contrainte,
modificateur ou shape keys, déjà placé près du corps **en pose de référence**.
Les deux meshes ont une UV map active dans une seule tuile 0–1. Les groupes
déformants verrouillés sont refusés ; les groupes auxiliaires sont conservés.

Adapter [garment-fit.json](examples/garment-fit.json) aux noms réels des objets,
action et os. Le mapping explicite réutilise Animation Doctor, y compris `action_slot`
pour les actions à slots. L'intervalle inclut ses deux extrémités. Limites :
10 000 sommets de vêtement, 50 000 sommets de corps, 120 frames échantillonnées,
1–8 influences, masque UV 32–512 pixels et durée du worker 600 s maximum.

```powershell
$env:PYTHONPATH = (Resolve-Path .\scripts\addons_core).Path
py -3.13 -m cryptonyan_asset_studio.garment_fit C:\CryptoNyanWork\outfit-source.blend C:\CryptoNyanWork\garment-fit.json --output C:\CryptoNyanWork\fit-001 --blender 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --timeout 120
```

Adapter le chemin au Blender effectivement installé. Le processus isolé utilise
`--disable-autoexec`, une copie de source et les contrôles de délai existants.
Le transfert interpole les poids des trois sommets du triangle du corps le plus
proche, retient les plus grandes influences puis les normalise. L'ajustement ne
rapproche pas arbitrairement tout le vêtement : il corrige les sommets trop proches
ou intérieurs vers la distance `clearance_m`, sous le plafond `max_distance_m`.
Les éléments trop éloignés sont refusés. Il ne crée pas de topologie, d'épaisseur,
de patrons de couture ou de simulation textile.

Sorties : `candidate.blend`, `garment.json`, `result.json`, `body-uv-mask.png`,
`garment-uv-mask.png`, copie source et spécification. `CN_GarmentCandidate` est le
nouvel objet ; le vêtement original est masqué uniquement dans cette copie.
Les poids du candidat sont relus après sauvegarde/réouverture dans le worker.

Le rapport indique les déplacements, l'audit des poids et, par frame, le nombre
et les 100 premiers sommets à distance signée négative du corps évalué. La commande
rend 1 si des poses contiennent ces sommets ; le candidat demeure disponible pour
correction. **L'absence de sommets intérieurs ne garantit pas l'absence de traversée
de triangles, d'auto-intersection ou de défaut entre deux frames.** Les plis, poses
extrêmes, contacts et coutures demandent une revue. Aucun certificat de cloth collision.

Les PNG sont des masques RGB d'occupation UV, pas des textures artistiques, des
normal maps, des images de référence du chat ou des wireframes UV. Ils peuvent
alimenter les [profils ComfyUI à références explicites](comfy-references.md).
Après correction visuelle, utiliser ton exporteur skeletal habituel et importer
le vêtement comme **nouvel asset** sur le Skeleton existant ; le publisher statique
GLB n'est pas adapté à cette opération. Ajouter son chemin à `wardrobe.json`.

Tests exécutables :

```powershell
$env:LOOPCUT_BLENDER = 'C:\chemin\vers\blender.exe'
py -3.13 -m unittest discover -s loopcut/tests -p test_cryptonyan_garments.py -v
```

Les fixtures synthétiques fermées passent sous Blender Linux 4.3.2. La version
Blender de ton PC, le vrai personnage et les exports Unreal restent à qualifier.
