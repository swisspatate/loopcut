# Matériaux par couches — v0.26

Créer une variante PBR d'un asset existant en superposant des matériaux sous des
masques : neige, poussière, peinture, camouflage, usure ou accents de skin. Le même
masque peut piloter plusieurs canaux. L'ordre des couches et l'opacité sont explicites.
Le résultat est un `material.json` standard réutilisable par les outils Blender,
World PBR et les [variantes Unreal](unreal-material-variants.md) existants.

## Sources : Ucupaint, ComfyUI ou textures peintes

[Ucupaint](https://github.com/ucupumar/ucupaint) est un éditeur de couches pour Blender.
La révision étudiée est `3b280e8a874023e4f882be52fbf2d46a32ac6402` :
[README](https://github.com/ucupumar/ucupaint/blob/3b280e8a874023e4f882be52fbf2d46a32ac6402/README.md),
[COPYING GPLv3](https://github.com/ucupumar/ucupaint/blob/3b280e8a874023e4f882be52fbf2d46a32ac6402/COPYING).
L'extension peut être installée séparément via Blender Extensions et ses couches
exportées en PNG. Notre compositeur est indépendant : aucun code Ucupaint copié,
aucune installation automatique ni contrôle de son graphe de nœuds. L'échange
s'effectue par les cartes PBR exportées. Les UDIM, height/displacement et groupes
Ucupaint natifs ne sont pas interprétés.

ComfyUI peut fournir les PNG via les profils configurés existants. Construire les
bundles avec les canaux réellement produits ; une image couleur seule ne fournit
pas de normale ou de roughness. Garder les reçus ComfyUI avec les sources : cette
version capture les cartes et leurs hashes, pas les preuves de génération/licence
externes. Elle ne soumet aucun nouveau workflow ComfyUI.

Chaque matériau d'entrée est un bundle [Material Doctor](material-pipeline.md)
avec un `material.json` et ses cartes. Un masque est un PNG RGB gris opaque : noir
conserve la base, blanc applique la couche, gris interpole. Toutes les cartes et
masques partagent dimensions et coordonnées UV. Pas de redimensionnement implicite.

## Créer une recette dans PowerShell

Exemple avec deux bundles placés dans `D:\CryptoNyanWork\layer-sources\base` et
`...\snow`, et un masque `snow-mask.png` dans ce même dossier de sources. Pour
créer ces bundles à partir de PNG, utiliser `materials pack` du guide Material Doctor.

```powershell
$env:PYTHONPATH = "$PWD\scripts\addons_core"
$layerSources = 'D:\CryptoNyanWork\layer-sources'
$layerRecipe = @{
  schema = 'cryptonyan.material-layers/1'
  id = 'temple-snow'
  base = @{
    file = 'base/material.json'
    sha256 = (Get-FileHash "$layerSources\base\material.json" -Algorithm SHA256).Hash.ToLowerInvariant()
  }
  layers = @(@{
    id = 'snow'
    material = @{
      file = 'snow/material.json'
      sha256 = (Get-FileHash "$layerSources\snow\material.json" -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    mask = @{
      file = 'snow-mask.png'
      sha256 = (Get-FileHash "$layerSources\snow-mask.png" -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    opacity = 0.8
    channels = @('base_color', 'roughness', 'normal')
    blend = 'mix'
  })
}
$layerRecipe | ConvertTo-Json -Depth 12 | Set-Content -Encoding utf8 D:\CryptoNyanWork\snow-layers.json
python -m cryptonyan_asset_studio.material_layers prepare D:\CryptoNyanWork\snow-layers.json --source-root $layerSources --output D:\CryptoNyanWork\snow-prepared
python -m cryptonyan_asset_studio.material_layers check D:\CryptoNyanWork\snow-prepared
python -m cryptonyan_asset_studio.material_layers compose D:\CryptoNyanWork\snow-prepared --output D:\CryptoNyanWork\snow-material-v01
```

Chaque canal choisi doit exister dans la base **et** la couche. Les canaux non choisis
restent ceux de la base ; leurs PNG sont conservés à l'identique. `multiply` permet
une multiplication sous masque pour les couleurs/scalaires ; les normales acceptent
seulement `mix`. Ajouter d'autres entrées à `layers` pour empiler les effets.

`prepare` fige les sources et masques, vérifie les hashes et publie un `plan.json`.
`compose` peut ensuite fonctionner sans les dossiers originaux. Garder cette
préparation pour reproduire le résultat. L'export contient les cartes aplaties,
`material.json` et `layers.json` avec recette, hashes et algorithme.

Dans Blender : **Vue 3D → CryptoNyan → Matériaux par couches**. Choisir la recette,
les sources, un nouveau dossier de préparation puis un nouveau dossier PBR. Les
boutons exécutent les mêmes fonctions que la CLI ; la composition est synchrone.
Utiliser ensuite l'application PBR existante sur une copie de l'asset, ou importer
le bundle via l'adaptateur Unreal déjà documenté. Le panneau ne peint pas les masques.

## Règles numériques et périmètre

- Jusqu'à 8 couches, 1 048 576 pixels par image et 16 M échantillons de canaux au
  total ; 128 Mio de fichiers d'entrée. PNG RGB/RGBA 8 bits non entrelacés. Les cinq
  filtres PNG sont décodés. L'alpha doit être opaque, y compris sur les masques.
- Poids = gris du masque / 255 × opacité. Les couleurs sRGB sont converties en
  linéaire avant le mélange ; scalaires et masques sont traités comme données.
  L'algorithme suit les rôles du manifeste, sans interpréter les profils ICC/gamma
  facultatifs des PNG. Les cartes scalaires doivent être des RGB gris.
- Normales tangentes OpenGL +Y, hémisphère supérieur ; mélange linéaire normalisé.
  Les pixels à poids 0/1 conservent les valeurs de l'entrée sélectionnée. Ce mélange
  remplace progressivement une normale ; l'ajout de microdétails par RNM, les
  normales issues de height et la conversion DirectX restent à développer.
- Les intermédiaires sont quantifiés en 8 bits après chaque couche. L'ordre compte.
  Aucun jugement de qualité physique, de raccord UV ou de couture n'est produit.
- Les dossiers de sortie doivent être nouveaux et séparés des entrées. Une erreur
  de préparation retire le nouveau dossier incomplet. Une erreur d'export peut
  laisser un bundle partiel : utiliser une nouvelle destination et consulter le
  reçu `layers.json`, qui n'est écrit qu'après la composition réussie.
- Un matériau pour plusieurs assets nécessite des UV compatibles ou un travail
  d'adaptation/bake propre à chaque asset. La composition ne recalcule pas les UV.

Validation Windows/Unreal et vrais matériaux : [checklist locale](local-pc-checklist.md).
