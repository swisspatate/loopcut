# Atelier d'amélioration du jeu existant

Le travail porte sur le personnage riggé et les niveaux existants de CryptoNyanRun.
Les six chantiers acceptés sont suivis ici, en distinguant le code livré de la
qualification sur les vrais assets et des développements suivants.

| Chantier | État après v0.29 | Étape suivante |
| --- | --- | --- |
| Contexte de scène sélectionnée | Snapshots Blender, métadonnées, capture via Loopcut et lecture/image MCP | Valider la capture GPU Windows et la lisibilité du vrai personnage/niveau. |
| Zones à modifier | Éditeur local de masques sur image, replay vérifié, MCP et raccord couches PBR/entrées ComfyUI existantes | Peinture sur la surface 3D, projection UV et bords doux. |
| Workflows TRELLIS | Contrat GLB local, contrôle des sources et profils ComfyUI déjà disponibles | Obtenir les exports API des workflows réels, mapper les nœuds/fichiers et ajouter la collecte 3D. |
| Kits de niveaux procéduraux | v0.28 : graphe de salles, checkpoints obligatoires, branches/boucles, portes/proxies, kit démo, aperçu GLB et garde de bornes Unreal | Qualification du contrôleur/NavMesh, placement sur terrain, étages et PCG/HISM natif. |
| Skins pendant l'animation | v0.29 : essayage multi-actions de vêtements riggés, distances/traversées échantillonnées, audits, rapport et copies aux pires poses | Qualifier le vrai personnage/shape keys ; collisions vêtement/vêtement, détection continue et retouches restent à développer. |
| Comparaison dans Unreal | Variantes de matériaux, cartes/séquences de revue et restauration ciblée existantes | Scène de comparaison commune, mesures GPU et adoption contrôlée après qualification locale. |

Guides livrés : [sélection](scene-selection.md), [masques](mask-paint.md),
[couches](material-layers.md), [caméras](camera-moves.md),
[versions](visual-versions.md), [niveaux modulaires](modular-levels.md),
[essayage animé](animated-wardrobe.md). La [checklist PC](local-pc-checklist.md) centralise
les essais sur Windows, Blender, ComfyUI et Unreal. Les cases non cochées ne sont
pas présentées comme des validations accomplies dans le cloud.
