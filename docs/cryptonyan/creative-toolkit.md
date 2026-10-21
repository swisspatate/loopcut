# Atelier créatif — v0.11

L'atelier génère de vrais fichiers Blender et un chat en GLB animé. Il ajoute des
composants C++ au plugin Unreal existant. Ce sont des prototypes stylisés réutilisables,
avec des limites explicites, pas des assets artistiques finalisés.

| Domaine | Fonction livrée | Limite actuelle |
| --- | --- | --- |
| Bâtiments | 8 modules : sol, mur, porte, fenêtre, toit, pilier, escalier, passerelle ; assemblage de 1–4 étages | Circulation, collisions, garde-corps et hauteur libre à revoir ; pas de parcours certifié |
| Montagnes | Relief déterministe, place centrale, heightfield 16 bits | Pas de grottes, d'érosion hydraulique ou de conversion automatique vers Landscape |
| Liquides | Eau/lave avec surface et vague animées | Pas de simulation de fluide, flottabilité ou propagation |
| Décor vivant | Croissance animée de cristaux | Pas de générateur général de végétation |
| Éclairage | Jour, coucher de soleil, nuit ; soleil, éclairage d'accent, caméra | Régler séparément les valeurs et l'exposition Blender/Unreal |
| Météo | Pluie, neige, cendres ou ciel clair ; particules Blender et instances Unreal | Volume fixe, sans occlusion par les toits ni budget GPU mesuré |
| Effets | Six atlas RGBA de 16 images, anneaux et particules Blender, effets Unreal à instances | Niagara accepte des systèmes existants ; aucun graphe `.uasset` n'est généré |
| Chat | Mesh pondéré, quatre jambes IK, contrôles de pattes/pôles, oreilles et queue | Pondération rigide par segment ; pas d'auto-rig d'un chat importé |
| Animations | Repos, course, saut, réception, dash, freinage ; six clips GLB avec skin | Sur place, sans root motion ; contact au sol et contrôleur à adapter |
| Pouvoirs | Six éléments ; dash, impact, projectile, zone | Démonstration solo, sans dégâts, sauvegarde ou réplication réseau |
| Menu | UMG en C++ : éléments, énergie et quatre formes de pouvoir | Pas d'inventaire, carte, progression ou habillage final |

## Générer le kit

Depuis un checkout complet, Python 3.11+ et le vrai exécutable Blender :

```powershell
$env:PYTHONPATH = (Resolve-Path .\scripts\addons_core).Path
$env:LOOPCUT_BLENDER = 'C:\Tools\Loopcut\blender.exe'
$creativeRoot = Join-Path $env:LOCALAPPDATA 'CryptoNyanCreative'
New-Item -ItemType Directory -Force $creativeRoot | Out-Null

py -3.13 -m cryptonyan_asset_studio.creative_kit plan `
  .\docs\cryptonyan\examples\creative-kit.json --destination "$creativeRoot\Plan"
py -3.13 -m cryptonyan_asset_studio.creative_kit build `
  .\docs\cryptonyan\examples\creative-kit.json --destination "$creativeRoot\Kit" `
  --blender $env:LOOPCUT_BLENDER --timeout 180
py -3.13 -m cryptonyan_asset_studio.creative_kit check "$creativeRoot\Kit"
```

Les destinations doivent être nouvelles. `plan` ne lance pas Blender. `build` réutilise
le worker isolé et les limites de processus ; aucun `.blend` source n'est ouvert.
Un échec peut laisser des sorties partielles, mais pas un catalogue de succès.

- `architecture.blend` : galerie des huit modules nommés, UV et matériau partagé.
- `environment.blend` : bâtiment, montagnes, liquide, effets, cristaux, météo,
  éclairage et caméra. Lire la timeline entre les images 1 et 61.
- `cat.blend` : rig et skin ; actions `CN_idle`, `CN_run`, `CN_jump`, `CN_land`,
  `CN_dash`, `CN_brake` dans le Dope Sheet/Action Editor.
- `cat.glb` : skin et six animations, contraintes échantillonnées par le glTF Blender.
  Les contrôles IK Blender ne deviennent pas automatiquement un Control Rig Unreal.
- `fx/<element>.png` : atlas 4×4, 16 frames en ordre ligne par ligne, 128×128 RGBA.
- `height.raw`, `height.json` : grille uint16 little endian et échelle en mètres.
  Le maillage de preview est abaissé de 0,22 m sous les sols.
- `plan.json`, `worker-report.json`, `creative.json` : recette, métriques et hashes.

`check` vérifie les fichiers après déplacement du kit, réutilise les contrôles GLB
de Loopcut et exige un skin/six clips. `engine_validated` reste faux. Les hashes
ne certifient ni l'origine, ni la qualité artistique, ni la jouabilité.
`kit_id` identifie la recette ; les textures optionnelles sont identifiées par les
hashes de l'inventaire et ne changent pas cet identifiant de recette.

Paramètres : `bays` 2–6 travées de 3 m, `floors` 1–4 étages de 3 m,
`terrain_grid` 33/65/129, taille 32–256 m, relief 1–64 m, seed entière 32 bits.
Biomes : `volcanic`, `ice`, `forest`, `neon`. Éclairage : `day`, `sunset`, `night`.
Météo : `clear`, `rain`, `snow`, `ash`. Liquide : `water`, `lava`.

Les sockets sont un contrat métrique pour modules droits, pas un graphe de navigation.
Les escaliers montent 3 m en dix marches de 30 cm : adapter leur dimensionnement au
personnage. Revoir croisements, paliers, portes, bords de toit et passages sous escalier.

## Réutiliser ComfyUI et le publisher

Passer le `material_manifest` retourné par [texture_collect](comfy-agent-profiles.md)
au constructeur :

```powershell
py -3.13 -m cryptonyan_asset_studio.creative_kit build `
  .\docs\cryptonyan\examples\creative-kit.json --destination "$creativeRoot\KitTextured" `
  --blender $env:LOOPCUT_BLENDER --material 'D:\Textures\material\material.json'
```

Le matériau est copié, vérifié et incorporé aux modules et au bâtiment ; budgets
partagés avec l'aperçu PBR : 64 MiB de cartes et 16 777 216 pixels de canaux.
Terrain, liquide, effets et chat gardent leurs matériaux dédiés. Ce jalon n'ajoute
pas d'outil MCP pour construire le kit : les agents peuvent utiliser sa CLI locale.

Un module statique peut utiliser le publisher existant :

```powershell
py -3.13 -m cryptonyan_asset_studio --workspace "$creativeRoot\PublishJobs" `
  --asset-root "$creativeRoot\Kit" --executor blender --blender $env:LOOPCUT_BLENDER `
  publish architecture.blend --object door
```

Le chat animé utilise une livraison distincte de l'importeur statique, qui refuse
skins et animations. Tester son import Unreal dans un dossier neuf : aucun import
de squelette n'est automatisé ici. Pour Landscape, vérifier/rééchantillonner la
heightmap et son échelle ; ses dimensions ne sont pas déclarées compatibles nativement.

## Compiler et essayer Unreal

Copier `integrations/unreal/CryptoNyanRuntime` dans `Plugins/CryptoNyanRuntime` d'un
projet C++ de test. Activer Niagara et Python Editor Script Plugin, puis compiler avec
UnrealBuildTool/UHT. UMG, Slate et Niagara sont déclarés comme dépendances. Le plugin
complet n'a pas été compilé ni exécuté dans le cloud ; c'est une validation locale.

Créer et enregistrer une carte vide `/Game/CryptoNyan/ReviewMaps/Elements01`.
Le script refuse une autre carte, une carte contenant des acteurs autres que
WorldSettings, un reçu existant ou un dossier de destination existant.

Plan hors moteur :

```powershell
py -3.13 -m cryptonyan_asset_studio.unreal_creative --report "$creativeRoot\UEPlan.json"
```

Dans la console Python Unreal, adapter les chemins et créer d'abord le dossier parent
du reçu :

```python
import sys
sys.path.insert(0, r'C:\src\loopcut\scripts\addons_core')
from cryptonyan_asset_studio.unreal_creative import review
print(review(r'C:\CryptoNyanReview\elements-apply.json', apply=True,
             target_level='/Game/CryptoNyan/ReviewMaps/Elements01'))
```

Le script crée un matériau `Tint`, cinq surfaces réactives, un sol, un PlayerStart
et une atmosphère avec neige. Il sauvegarde uniquement le nouveau matériau et laisse
la carte non sauvegardée. Contrôler avant de sauvegarder. Un échec conserve un reçu
des créations partielles ; aucune suppression/annulation automatique n'est tentée.

Dans le Blueprint du personnage de test :

1. Ajouter `CryptoNyanPowerComponent` et lui attribuer `M_Element` comme `EffectMaterial`.
2. Sur une touche de menu, appeler `Open Power Menu` avec le PlayerController local.
3. Choisir un élément puis Projectile, Impact, Zone ou Dash. Dash nécessite un `Character`.
4. Fermer pour reprendre le contrôle normal. Le menu ne met pas le monde en pause.

On peut aussi relier `ActivatePower` à Enhanced Input avec une direction. Le menu
utilise l'avant du personnage, pas la visée caméra. Énergie 100, coût par défaut 10,
récupération 8/s, cooldown par défaut 0,5 s ; paramètres bornés à l'exécution.

## Interactions

| Action | Condition | Réaction |
| --- | --- | --- |
| Eau | Surface réactive | Devient humide |
| Glace | Humide + gelable + non brûlée | Gèle ; le liquide commence à bloquer le Pawn |
| Feu | Gelée | Dégèle et reste humide |
| Feu | Humide, non gelée | Sèche ; un prochain feu peut brûler |
| Feu | Sèche + inflammable | Cache le mesh et retire sa collision |
| Électricité | Conductrice ou humide | Active `Charged` et l'événement Blueprint |
| Terre | Déplaçable + non brûlée | Demande une montée, jusqu'à 500 cm, avec sweep |
| Vent | Déplaçable + non brûlée | Pousse de 150 cm dans la direction, avec sweep |

`OnElementChanged` permet de brancher portes, sons ou objectifs. Il n'y a pas encore
de réseau de conduction ni de dégâts au joueur. Les états persistent jusqu'à
`ResetElements`. La glace ne vérifie pas l'occupation par un Pawn : tester ce cas.
Un sweep peut bloquer une montée/poussée ; `Raised` décrit l'état demandé, pas une
garantie d'arrivée à la destination.

Une zone affecte au plus 64 surfaces différentes, une seule fois chacune, pendant
trois secondes ; recherche toutes les 0,25 s. Projectile balayé à 1 500 cm/s, durée
trois secondes. Effets natifs : 24 instances ; météo : 96. Tester collisions,
passagers, framerates faibles, volumes occupés et charge simultanée localement.

Attribuer des NiagaraSystem existants dans `NiagaraEffects` pour enrichir le rendu.
Le runtime transmet `User.Color` s'il existe et détruit le composant après trois
secondes, même si le système boucle. Les atlas peuvent servir de SubUV 4×4 dans
un matériau/Niagara configuré localement. ComfyUI peut fournir d'autres sprites avec
un profil adapté ; il ne construit pas automatiquement les graphes Niagara.
Les composants refusent l'activation réseau : multijoueur, prédiction et sauvegarde
des états restent à développer.

## Validation et suites

Les tests ouvrent les trois `.blend`, vérifient UV/PBR, instances, vagues, effets,
IK, pondération, poses finies, boucles repos/course, absence de root motion et GLB.
Ils déplacent le kit et suppriment les textures sources avant vérification.
Les règles élémentaires/budgets/particules sont compilés en C++17 ; cela ne compile
pas les classes Unreal/UHT. Le script d'éditeur est testé contre un faux éditeur.

Voir la [checklist PC](local-pc-checklist.md). Restent des développements : skin
organique et rig du chat définitif, retargeting/Control Rig, root motion, fluides
physiques, grottes, navigation architecturale certifiée, Niagara généré,
inventaire/progression et réseau. Ces fonctions ne sont pas cachées derrière une
simple validation locale.
