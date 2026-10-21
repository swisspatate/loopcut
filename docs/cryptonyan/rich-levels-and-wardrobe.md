# Niveaux riches et garde-robe — v0.20

Cette extension assemble **tes assets existants** et prépare des variantes dans une
carte de revue vide. Les recettes sont des fichiers JSON réutilisables ; elles peuvent
être écrites par Claude Code/Codex, puis exécutées par les commandes ci-dessous.
Ce sont des outils CLI/Python opt-in, pas de nouveaux boutons ni outils MCP natifs Loopcut.
Les appels ComfyUI continuent à passer par le serveur MCP existant.

## Niveaux

Adapter [rich-level.json](examples/rich-level.json) aux assets présents sur ton PC.
Tous les chemins d'exemple sont fictifs. Les unités des recettes sont les mètres,
les angles les degrés ; l'adaptateur convertit en centimètres pour Unreal.

| Fonction | Comportement implémenté |
| --- | --- |
| Décoration | Dispersion à seed stable par zone, choix de modules, taille et rotation variables |
| Passages réservés | Volumes `clearances` exclus pour les meshes ; boîtes orientées ramenées en AABB conservatrices |
| Bâtiments | Grille de cellules, étages, sols, murs périphériques, toit et une entrée ouverte au rez-de-chaussée |
| Repères | Assemblages de pièces autour d'une position, avec mécanisme optionnel |
| Ambiances | Matériaux MIC par module, soleil, brouillard, météo, lumières ponctuelles, SoundWave et NiagaraSystem existants |
| Plateformes | Réutilisation de `CryptoNyanPlatform`, oscillation verticale, réservation du volume balayé |
| Variantes | Changer `theme` conserve la géométrie et les seeds ; `Night`, `Snow`, `Abandoned`, `Corrupt` sont des recettes éditables |

Les modules doivent avoir un **pivot centré et les demi-dimensions exactes** de
`half_m`. Unreal vérifie leur bounding box avant le placement. Pour un module dont
le pivot est différent, préparer une copie centrée dans Blender et actualiser la
recette. Les plateformes utilisent une collision cuboïde : ne pas leur affecter
un mesh concave ou une forme dont cette boîte serait trompeuse.

Une zone de dispersion est un rectangle XY à hauteur constante, avec au plus
256 objets ; au maximum 512 acteurs sont planifiés. Le compilateur refuse une
densité qui ne tient pas dans l'espace déclaré. Il ne projette pas les objets sur
un terrain et ne certifie pas le chemin du personnage. Les modules structurels
peuvent se toucher/se recouvrir ; leurs proportions, ouvertures, raccords et
collisions se vérifient visuellement. **Escaliers et accès aux étages restent des
modules à composer dans `landmarks.parts`**, pas un réseau de navigation généré.

Les ambiances réutilisent les acteurs et effets existants ; aucun graphe Niagara,
son ou matériau artistique n'est inventé par ce compilateur. La dispersion utilise
les volumes déclarés, pas le NavMesh. Une carte de revue séparée par variante est
recommandée. L'assemblage final dans tes niveaux se fait après cette revue.

### Mécanismes réutilisables

Le plugin ajoute `ACryptoNyanMechanism`, spécialisé depuis les surfaces élémentaires.
`ConfigureMechanism(Kind, Element, Strength, HalfExtentCm)` est disponible en Blueprint
avant BeginPlay. La recette effectue la conversion d'unités et d'énumérations.

| `kind` (index) | Effet solo |
| --- | --- |
| `gate` (0) | Cube bloquant qui disparaît à réception de l'élément choisi |
| `breakable` (1) | Destruction en une activation, même logique ; pas de fracture Chaos ni débris |
| `wind` (2) | Impulsion suivant le haut de l'acteur, proportionnelle au temps, force bornée |
| `gravity` (3) | Multiplicateur de gravité, limité à 0,1–2, restauré en sortie/destruction |
| `ice` (4) | Friction et facteur de freinage réduits, restaurés en sortie/destruction |
| `beacon` (5) | Événement `OnActivated(Visitor)` une fois au premier personnage entrant |

Les éléments sont `fire`, `ice`, `earth`, `wind`, `water`, `electric` (indices 0–5).
Les portes/murs reçoivent les pouvoirs via la méthode virtuelle `ApplyElement`
existante ; leur événement porte un `Visitor` nul. Relier `OnActivated` dans le
Blueprint local pour déclencher une animation, un objectif ou une cutscene existante.
`ResetElements` restaure les visiteurs et réarme le mécanisme.
Les zones attendent un `ACharacter` et ses overlaps. Gravité/glace ne se cumulent
pas : un tag réserve temporairement le mouvement, et une propriété modifiée par
un autre système n'est pas écrasée à la restauration. Maximum 32 visiteurs par zone.
Le runtime est **solo**, sans réplication. Tester entrées/sorties, destruction,
chevauchement de zones et compatibilité avec le contrôleur du jeu.

Les plateformes demandent un matériau explicite pour leur module, amplitude
0–3 m, période 0,1–20 s et phase positive strictement inférieure à la période.
Les passages protégés ne peuvent pas croiser leur volume balayé.

## Tenues et skins

Adapter [wardrobe.json](examples/wardrobe.json) avec le corps et le squelette existants :

- `materials` remplace des slots sur **l'acteur de revue** par des MIC existants ;
- `accessories` attache des StaticMesh à des os/sockets nommés, avec offsets ;
- `garments` attache des SkeletalMesh utilisant le même Skeleton, liés à la pose du corps ;
- `outfit` sélectionne une tenue parmi 32, `animation` un clip parmi 16.

Le catalogue JSON conserve les tenues. L'adaptateur crée une prévisualisation
animée Single Node, sans collisions, notifies, post-process AnimBlueprint ou cloth
simulation. Les sockets, slots et Skeleton sont vérifiés avant création. Le partage
d'un Skeleton ne suffit pas à garantir la bonne déformation : références de pose,
hiérarchie, os effectivement présents, LOD et clipping se vérifient sur le personnage.
Un menu de garde-robe en jeu, l'inventaire, les déblocages et la sauvegarde joueur
restent des développements distincts. Aucun changement du Blueprint du héros ici.

Pour créer les vêtements : [ajustement et poids dans Blender](garment-workflow.md).
Pour décliner des skins : [références ComfyUI](comfy-references.md), puis collections
de textures et variantes de matériaux existantes. Les textures seules ne créent
ni un vêtement 3D ni un rig.

## Commandes PowerShell et Unreal

Depuis le dépôt, avec des chemins locaux adaptés :

```powershell
$env:PYTHONPATH = (Resolve-Path .\scripts\addons_core).Path
py -3.13 -m cryptonyan_asset_studio.scene_recipes C:\CryptoNyanWork\rich-level.json --project C:\Games\CryptoNyanRunUnreal --output C:\CryptoNyanWork\level-plan.json
py -3.13 -m cryptonyan_asset_studio.scene_recipes C:\CryptoNyanWork\wardrobe.json --project C:\Games\CryptoNyanRunUnreal --output C:\CryptoNyanWork\outfit-plan.json
py -3.13 -m cryptonyan_asset_studio.unreal_scenes C:\CryptoNyanWork\level-plan.json --report C:\CryptoNyanWork\level-dry.json
```

Le projet doit avoir ses fichiers LFS téléchargés. Les plans fixent l'identité du
projet et les hashes des assets/sidecars, puis les revérifient avant/après placement.
Les sorties doivent être neuves et hors du projet. Refaire un plan si une source change.

Compiler le plugin `CryptoNyanRuntime` v0.3, activer Python Editor Script Plugin et
Editor Scripting Utilities. Dans Unreal 5.8, ouvrir exactement la carte de revue
choisie, vide hormis WorldSettings, avec tous les assets sauvegardés. Dans la console Python :

```python
import sys
sys.path.insert(0, r"C:\Dev\loopcut\scripts\addons_core")
from cryptonyan_asset_studio.unreal_scenes import execute
result = execute(r"C:\CryptoNyanWork\level-plan.json", r"C:\CryptoNyanWork\level-result.json", apply=True)
print(result)
```

Même appel pour la tenue dans sa propre carte. Le résultat attendu est
`placed_review_required`. Le code ne sauvegarde pas la carte ni les assets sources.
En cas d'échec, seuls les acteurs créés par cet appel sont retirés ; le reçu indique
toute suppression échouée. Après examen, sauvegarder la carte de revue manuellement.
La répétition sur une carte occupée est refusée, pas une opération de mise à jour.

Les tests ici vérifient le compilateur, les règles C++ sans moteur et un double
strict du protocole éditeur. La compilation UHT, le rendu, les attachments réels,
la lecture animée et le gameplay ne sont pas validés dans Unreal cloud.
Voir la [checklist PC v0.20](local-pc-checklist.md#920--niveaux-riches-tenues-et-références-comfyui-v020).
