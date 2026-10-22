# Références, UV et masques vers ComfyUI — v0.20

Depuis v0.36, l'agent peut [préparer ses propres sélections](comfy-reference-preparations.md)
avec des PNG sous les racines autorisées, dans les slots définis par l'opérateur.
Ce guide conserve le parcours de profils à références fixes, compatible avec les
collections existantes. Les deux modes ne se mélangent pas dans un même profil.

Un profil peut désormais fixer jusqu'à trois PNG : `reference`, `uv` et `mask`.
L'agent choisit ce profil et son prompt/seed avec les outils texture MCP existants.
Les fichiers sont contrôlés avant chaque nouvelle soumission, et leurs hashes sont
conservés dans les reçus de demande et de résultat. La collecte conserve les
contrôles PNG/PBR de Material Doctor et l'idempotence des demandes.

## Préparer un profil local

1. Configurer un workflow fonctionnel dans ComfyUI, avec les modèles souhaités,
   puis exporter son JSON **API** et l'enregistrer dans un catalogue de
   [profils configurables](comfy-agent-profiles.md). Aucun modèle n'est préinstallé.
2. Le graphe doit déjà consommer les images nécessaires via des nœuds `LoadImage`.
   Choisir soi-même les connexions de référence/image-to-image/conditionnement,
   masque et guidage UV appropriées au modèle. Ce module ne fabrique pas ces graphes.
3. Adapter [comfy-references.json](examples/comfy-references.json) avec les vrais
   chemins PNG et IDs de nœuds. Un binding est exactement `[node_id, "image"]`.
   Les images sont RGB/RGBA 8 bits, non entrelacées, au plus 4096×4096 et 32 MiB
   chacune, 64 MiB pour le lot. Retirer les rôles inutilisés.
4. Exécuter la préparation sur le **même PC que ComfyUI**, en ciblant son vrai dossier
   `input` existant. Aucun serveur distant ni upload réseau implicite.

```powershell
$env:PYTHONPATH = (Resolve-Path .\scripts\addons_core).Path
py -3.13 -m cryptonyan_asset_studio.comfy_references C:\CryptoNyanWork\profiles\profiles.json skin-reference C:\CryptoNyanWork\comfy-references.json --input-root C:\ComfyUI\input --output C:\CryptoNyanWork\skin-profile-001
py -3.13 -m cryptonyan_asset_studio.comfy_profiles C:\CryptoNyanWork\skin-profile-001\profiles.json
```

Le dossier de sortie doit être neuf. Le préparateur modifie seulement les littéraux
`LoadImage.image` explicitement désignés, écrit le graphe dérivé et son hash, puis
un catalogue compatible avec le service existant. Les modèles et connexions restent
ceux du workflow choisi. Les images deviennent `cn_<sha256>.png` sous `input` ;
les fichiers de même nom sont vérifiés et jamais écrasés. Un échec peut laisser
le nouveau dossier et des images préparées ; ils ne déclenchent aucun calcul.

Le catalogue ajoute `input_root` (chemin absolu local) et, par profil,
`reference_inputs` (rôle, fichier, SHA-256, binding). Les anciens catalogues sans
ces champs restent compatibles. Ne pas déplacer ni modifier les fichiers tant
qu'un calcul est en attente : le contrôle a lieu avant l'envoi, pas au moment exact
où le GPU charge chaque image. Une copie du workflow ne prouve pas l'utilisation
sémantique des références : vérifier le graphe et l'effet visuel dans ComfyUI.

**Attention aux masques** : la sortie MASK de `LoadImage` dépend de l'alpha.
Pour les masques UV RGB blanc/noir exportés par Blender, brancher la sortie IMAGE
sur une conversion image-vers-masque dans le workflow, ou préparer un PNG avec
l'alpha voulu. Une image UV n'impose pas automatiquement le respect des coutures.

## Agent et lots de skins

Démarrer le serveur avec `--comfy-profiles` pointant vers le nouveau `profiles.json`,
comme dans le [guide MCP](comfy-agent-profiles.md). `texture_profiles` expose aussi
les références et leurs hashes ; aucun nouveau protocole n'est nécessaire.
Le parcours reste `texture_preflight` → `texture_submit` → `texture_status` →
`texture_collect`. Un même ID ne renvoie jamais un second POST, même si les images
changent ensuite. Une nouvelle demande ou un prévol refuse une référence modifiée.

Pour produire plusieurs skins, utiliser les [collections de textures](texture-collections.md)
avec ce profil, un style commun et une description/seed par variante. Les références
sont fixes pour toute la collection ; préparer un autre profil/lot pour un autre
UV layout ou une autre silhouette. Le prévol détecte les entrées/nœuds manquants,
et le lot s'arrête si le workflow personnalisé exige une revue.

Importer les résultats avec [les variantes Unreal](unreal-material-variants.md),
puis affecter les MIC aux slots de [tenues sauvegardées](rich-levels-and-wardrobe.md).
La génération GPU, les modèles/custom nodes, les licences réelles, les raccords UV,
la fidélité au personnage et les matériaux rendus restent à vérifier sur ton PC.
Les tests cloud utilisent un serveur simulé ; aucune image artistique générée
par un modèle n'est revendiquée pour cette version.
