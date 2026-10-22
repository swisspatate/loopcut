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

## Réalisé : tableau de références, v0.24

Le [tableau de références](reference-boards.md) ajoute des snapshots PNG contrôlés,
notes/rectangles, liens par hash aux assets existants, miniatures Blender, revue HTML,
lecture MCP avec images et préparation de recettes Image Workshop. Aucun code Mixar
n'est copié. Le tableau n'est pas encore un canevas libre à nœuds et ne lance pas
TRELLIS. Les rectangles ne recadrent pas les images ; l'agent les interprète.

## À développer ensuite

| Fonction | Base existante chez nous | Travail encore nécessaire |
| --- | --- | --- |
| Tableau de références | Snapshots, notes/zones, assets liés, interface Blender, MCP et HTML v0.24 | Tracé des zones à la souris, canevas libre et liens de missions durables |
| Liaison TRELLIS | GLB local contrôlé, client HTTP ComfyUI et reçus | Mapper les workflows réels de l'utilisateur, soumettre/suivre/collecter du GLB |
| Versions visuelles | v0.25 : index de candidats Workshop, fichiers vérifiés, comparaison HTML, sélection et restauration en copie | Versions de scènes/rigs arbitraires, captures interactives et adoption dans le jeu |
| Matériaux par couches | v0.26 : mélange PBR sous masques, snapshots, export aplati et panneau Blender ; étude Ucupaint | Peinture interactive, import de graphes Ucupaint, RNM, UDIM et displacement |
| Caméras Director | v0.26 : presets ligne/orbite, visée calculée, aperçu Blender et recette Sequencer existante | Cibles animées, collisions, optiques partagées et qualification Unreal réelle |
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

## v0.25 — Historique des candidats livré

[Versions visuelles](visual-versions.md) implémente indépendamment l'archivage
vérifié des candidats Image Workshop, la comparaison HTML des rendus/recettes,
une sélection explicite et la restauration dans un nouveau dossier, avec panneau
Blender et provenance facultative du tableau. Aucun code Mixar copié. Ce périmètre
ne couvre pas leurs checkpoints de scène générale ni leur backend.

Suite utile : matériaux en couches (évaluer Ucupaint et sa licence), mouvements de
caméra et qualification des workflows TRELLIS fournis par l'utilisateur. Le dessin
libre des tableaux et les versions de scènes/rigs arbitraires restent distincts.

## v0.26 — Couches et caméras livrées

[Matériaux par couches](material-layers.md) et [mouvements caméra](camera-moves.md)
sont des implémentations indépendantes réutilisant nos bundles PBR, validations
Loopcut et recettes Director. Ucupaint a été étudié à la révision
`3b280e8a874023e4f882be52fbf2d46a32ac6402` (README et COPYING GPLv3) ; le guide
explique l'échange de PNG exportés. Aucun code tiers ni service Mixar intégré.

Les autres points du tableau restent suivis : dessin libre, assemblage d'accessoires,
versions de scènes arbitraires et liaison TRELLIS aux workflows réels de l'utilisateur.
