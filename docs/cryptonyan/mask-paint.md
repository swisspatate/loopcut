# Masques interactifs sur image — v0.27

Peindre une zone sur une référence, une capture ou une texture UV : pinceau, gomme,
valeur grise, annulation/rétablissement et sauvegarde du tracé. L'éditeur est un
fichier HTML autonome qui s'ouvre localement dans le navigateur. Il ne contacte
aucun serveur. Le tracé JSON est ensuite réimporté pour créer un masque PNG vérifié.

**Une zone d'image n'est pas automatiquement une zone UV.** Pour un matériau PBR,
peindre sur une texture ou une mise en page UV correspondant réellement à l'asset.
Un masque sur une photo/capture peut guider un workflow image ComfyUI ; sa projection
sur un mesh nécessite un travail distinct.

## Parcours depuis Blender

1. Dans **CryptoNyan → Masques interactifs sur image**, choisir un PNG. Le bouton
   **Utiliser la référence du tableau** reprend la référence sélectionnée dans le
   tableau déjà chargé. Après un export de sélection avec viewport, l'image est
   aussi proposée automatiquement ici.
2. Choisir un nouveau fichier HTML hors des snapshots, par exemple
   `D:\CryptoNyanWork\editors\cat-mask.html`. Son dossier parent doit exister.
   **Créer l'éditeur local**, puis **Ouvrir dans le navigateur**.
3. Saisir une intention descriptive, par exemple « Neige sur les parties supérieures ».
   Peindre sur l'image : noir conserve la base, blanc applique la couche, gris mélange.
   Le rouge à l'écran est seulement la surimpression de prévisualisation.
4. **Enregistrer le tracé JSON** télécharge `cryptonyan-mask-strokes.json` dans le
   dossier choisi par le navigateur. **Reprendre un tracé** recharge ce JSON dans
   l'éditeur ; un fichier lié à une autre image est refusé.
5. Dans Blender, renseigner le JSON téléchargé et un nouveau dossier de sortie.
   Pour le rendre accessible à l'agent, utiliser la bibliothèque configurée :
   `D:\CryptoNyanWork\references\masks\cat-snow-01`.
   **Importer le tracé et produire le PNG** crée les fichiers vérifiés.

Le bundle contient `reference.png`, `strokes.json`, `mask.png` et `mask.json`.
La référence est copiée et identifiée par hash ; les traits sont rejoués pour
vérifier le masque. Le dossier doit être nouveau. Les boutons d'export refusent
une sortie dans le tableau ou l'instantané choisi depuis le panneau.

## CLI et accès par l'agent

```powershell
$env:PYTHONPATH = "$PWD\scripts\addons_core"
python -m cryptonyan_asset_studio.mask_paint editor D:\CryptoNyanWork\textures\cat-base-color.png --output D:\CryptoNyanWork\editors\cat-mask.html
python -m cryptonyan_asset_studio.mask_paint render D:\Downloads\cryptonyan-mask-strokes.json --reference D:\CryptoNyanWork\textures\cat-base-color.png --output D:\CryptoNyanWork\references\masks\cat-snow-01
python -m cryptonyan_asset_studio.mask_paint check D:\CryptoNyanWork\references\masks\cat-snow-01
```

Avec `reference_root` configuré et le client MCP reconnecté :

| Outil | Fonction |
| --- | --- |
| `reference_mask_list` | Liste les bundles vérifiés sous `reference_root/masks`. |
| `reference_mask_read(mask_id)` | Retourne le reçu, la référence liée, l'intention et les traits. |
| `reference_mask_image(mask_id, kind)` | Affiche le `mask` ou la `reference` comme image MCP. |

Les images MCP sont limitées à 2 Mio. Les lectures vérifient le bundle et ne lancent
pas de génération. `masks` est un sous-dossier réservé ; ne pas l'utiliser comme
identifiant d'un tableau dans cette bibliothèque.

## Raccord aux matériaux et à ComfyUI

Pour [les couches PBR](material-layers.md), copier `mask.png` dans le dossier des
sources de la recette et utiliser son hash dans `layers[].mask`. Les dimensions
doivent correspondre aux cartes et les UV doivent être adaptés. Le masque exporté
est un PNG RGB gris opaque, en données Non-Color.

Pour un profil ComfyUI compatible, le module existant `comfy_references` sait déjà
préparer les rôles `reference`, `uv` et `mask`. Exemple de déclarations à adapter
aux véritables IDs de nœuds du workflow approuvé :

```json
[
  {"role":"reference","path":"D:/CryptoNyanWork/references/masks/cat-snow-01/reference.png","binding":["10","image"]},
  {"role":"mask","path":"D:/CryptoNyanWork/references/masks/cat-snow-01/mask.png","binding":["11","image"]}
]
```

```powershell
python -m cryptonyan_asset_studio.comfy_references D:\CryptoNyanWork\comfy\profiles.json cat-inpaint D:\CryptoNyanWork\mask-bindings.json --input-root D:\ComfyUI\input --output D:\CryptoNyanWork\comfy\cat-snow-profile
```

Les bindings doivent viser des littéraux `LoadImage.image` existants. **Le masque
est dans les canaux RGB : le workflow doit convertir l'IMAGE grise en MASK** (par
exemple son nœud `ImageToMask` approprié). La sortie MASK de `LoadImage` fondée sur
l'alpha d'un PNG opaque ne représente pas notre dessin. Examiner ce raccord dans
ComfyUI avant soumission. Le rôle déclaré ne crée pas de conversion de graphe.

Le profil dérivé reste utilisable par le service textures existant, avec préflight,
modèles déclarés, prompt et seed. Aucun modèle/workflow n'est installé ou soumis
par l'éditeur de masque. Les workflows TRELLIS natifs nécessitent toujours leur
export API réel et un adaptateur de sorties 3D.

## Contrat du pinceau

PNG RGB/RGBA de référence, 8 Mio et 1 Mpx maximum ; jusqu'à 128 traits, 512 points
par trait et 4 096 points au total. Le rayon est exprimé en pixels de l'image,
indépendamment du zoom CSS. Le pinceau a des bords francs et des extrémités rondes ;
il remplace les pixels couverts par une valeur 0–255. La gomme écrit 0.

Les points sont normalisés depuis le coin supérieur gauche. Chaque segment couvre
les centres des pixels à distance inférieure ou égale au rayon. L'ordre des traits
compte. Le budget de calcul est borné à 32 M tests de pixels. Le replay JavaScript
et Python utilise le même algorithme et est comparé dans les tests.

La peinture directe sur la surface 3D, le raycast vers les UV, les bords doux,
la pression d'un stylet, les UDIM et les masques multi-zones nommées restent à
implémenter. La mise en page réelle du navigateur et le GPU du viewport se qualifient
sur ton PC : [checklist locale](local-pc-checklist.md).
