# Inspirations et portages Mixar

Référence étudiée : [Mixar-AI/mixar-app](https://github.com/Mixar-AI/mixar-app),
commit `e0575bb1b27d7c718bc90c6470326fb00dffc0d4`.
Le [README à cette révision](https://github.com/Mixar-AI/mixar-app/blob/e0575bb1b27d7c718bc90c6470326fb00dffc0d4/README.md)
précise que le dépôt contient le client Blender et que le backend IA hébergé reste
fermé. La compilation de l'ensemble implique leur fork Blender et ses ajouts C++.

## Réalisé : connexions des agents, v0.23

Inspiration fonctionnelle : le [parcours Connect MCP](https://github.com/Mixar-AI/mixar-app/blob/e0575bb1b27d7c718bc90c6470326fb00dffc0d4/src/scripts/mixar/modules/mcp_bridge/README.md).
Notre implémentation est indépendante : aucun fichier Mixar n'a été copié, aucun
logo ou service distant Mixar n'est utilisé. Elle réutilise `mcp_stdio`, la CLI,
`MissionBridge`, `load_catalog` et `LocalHTTP` du fork CryptoNyan.

Différence de portée : Mixar documente aussi un contrôle de son interface et des
outils de scène. Ici, le panneau configure notre MCP existant : missions sur fichiers
dans des workers séparés, textures et inventaire du projet. Aucun contrôle de la
scène ouverte, capture automatique du viewport ou annulation globale Blender n'est
ajouté. Guide : [agent-connections.md](agent-connections.md).

## À développer ensuite

| Fonction | Base existante chez nous | Travail encore nécessaire |
| --- | --- | --- |
| Tableau de références | Image Workshop, recettes et comparaison HTML | Images annotées, liens référence/asset/mission, interface Blender |
| Liaison TRELLIS | GLB local contrôlé, client HTTP ComfyUI et reçus | Mapper les workflows réels de l'utilisateur, soumettre/suivre/collecter du GLB |
| Versions visuelles | Sources hachées, candidats séparés, reçus et restauration de matériaux Unreal | Index de versions Blender, captures comparables, adoption/restauration explicite |
| Matériaux par couches | Bundles PBR, profils ComfyUI, variantes de skins | Étudier Ucupaint, composition de masques/couches et export versionné |
| Caméras Director | Plans de cutscene et adaptateur Sequencer | Adapter les mouvements Mixar isolables, conversion des repères et tests Blender/Unreal |
| Accessoires par emplacement | Wardrobe, sockets et audit de rig | Interface d'assemblage, prévisualisation et compatibilité avec le personnage réel |

Sources à examiner avant chaque portage : modules `moodboard`, `director`,
`space_mixie_chat/core/checkpoint_*` et [Ucupaint](https://github.com/ucupumar/ucupaint),
dont Mixar déclare dériver une partie de la peinture par couches.

## Réutilisation de code

Avant de copier un fichier, enregistrer sa révision, lire son en-tête SPDX et ses
dépendances, conserver les auteurs et notices et vérifier la compatibilité avec
notre composant GPL-3.0-or-later. Le dépôt contient notamment des fichiers GPL-2.0-or-later,
GPL-3.0-or-later et des dépendances sous d'autres licences : la licence globale ne
remplace pas cette vérification par fichier. Les éléments de marque ont une
[licence distincte](https://github.com/Mixar-AI/mixar-app/blob/e0575bb1b27d7c718bc90c6470326fb00dffc0d4/LICENSES/LicenseRef-Mixar-Brand.txt)
et ne doivent pas être intégrés à notre identité.

Les fonctionnalités dont le serveur est absent nécessitent notre propre
implémentation. Leur présence dans l'interface publique n'établit ni la disponibilité
du code complet ni une compatibilité locale démontrée.
