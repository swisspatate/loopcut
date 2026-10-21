# Générateurs image → 3D : étude d'intégration

Sources primaires consultées le 21 octobre 2026. Cette sélection documente les
interfaces possibles ; aucun de ces moteurs n'est installé, embarqué ni testé GPU
dans la v0.22. Le transfert local GLB est implémenté dans [Image Workshop](image-workshop.md).
Les performances ci-dessous sont les exigences annoncées en amont, pas nos mesures.

**Priorité confirmée par l'utilisateur : réutiliser ses workflows TRELLIS existants.**
Leur version et leurs nœuds d'export ne sont pas encore connus. Ne pas les remplacer
par Hunyuan ni supposer qu'il s'agit de TRELLIS.2. Les exigences du dépôt TRELLIS.2
ci-dessous ne sont pas un diagnostic de ces workflows locaux.

| Projet | Apport | Exigences annoncées / licence | Décision pour CryptoNyanRun |
| --- | --- | --- | --- |
| [Microsoft TRELLIS.2](https://github.com/microsoft/TRELLIS.2) | Objet depuis une image, matériaux PBR | README : Linux testé, GPU NVIDIA ≥24 Go ; code/modèle MIT, dépendances avec licences distinctes | Candidat pour machine adaptée ou service séparé. Ne pas promettre le fonctionnement sur une 5080 sans test d'un portage/offload précis. |
| [Tencent Hunyuan3D 2.1](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1) | Géométrie et peinture PBR séparées | README : 10 Go forme, 21 Go texture, 29 Go ensemble ; Community License spécifique | Évaluer d'abord la géométrie séparément, puis les textures. La licence doit convenir au lieu d'utilisation et à la distribution du jeu. |
| [Kijai ComfyUI-Hunyuan3DWrapper](https://github.com/kijai/ComfyUI-Hunyuan3DWrapper) | Nœuds ComfyUI et exemples de workflows | README : composants compilés de peinture, configurations Windows/Python/CUDA précises ; LICENSE.txt Tencent Hunyuan 3D 2.0 | Piste pour le prochain adaptateur ComfyUI GLB. Épingler commit, modèles et workflow API, puis tester sur le PC. Ne pas copier les nœuds dans Loopcut. |
| [Meta SAM 3D Objects](https://github.com/facebookresearch/sam-3d-objects) | Objets masqués d'une image, géométrie/texture/placement ; scènes avec occultations | Setup : Linux, GPU NVIDIA ≥32 Go ; checkpoints sur demande et SAM License | Piste pour découper une scène riche. Le splat PLY du démarrage rapide n'est pas accepté comme un mesh GLB : conversion/extraction de mesh à qualifier. |

Le [README TRELLIS.2](https://github.com/microsoft/TRELLIS.2#-installation) et sa
[licence](https://github.com/microsoft/TRELLIS.2/blob/main/LICENSE) sont les références
pour sa configuration. Les durées montrées en amont concernent un H100, pas le PC cible.

La [licence Hunyuan3D 2.1](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/blob/main/LICENSE)
et le [LICENSE.txt du wrapper](https://github.com/kijai/ComfyUI-Hunyuan3DWrapper/blob/main/LICENSE.txt)
excluent notamment l'UE, le Royaume-Uni et la Corée du Sud de leur territoire accordé.
Leurs clauses portent aussi sur certains usages des sorties : ne pas les traiter
comme de simples licences MIT ni déduire une compatibilité de distribution mondiale.
Aucun poids ni code de ces projets n'est redistribué par cette extension.

Pour SAM 3D, consulter le [setup](https://github.com/facebookresearch/sam-3d-objects/blob/main/doc/setup.md)
et la [SAM License](https://github.com/facebookresearch/sam-3d-objects/blob/main/LICENSE).
Une capacité de recherche sur des scènes occultées ne certifie pas des collisions,
une topologie de jeu, une échelle physique ou un rig réutilisable.

## Choix d'architecture

1. **Maintenant :** conserver le générateur hors de Blender/Loopcut. L'agent peut
   assembler des primitives ou fournir un GLB local avec référence, modèle et licence
   déclarés. Le contrat étroit est validé avant tout import.
2. **Prochaine intégration :** adaptateur ComfyUI pour un workflow API local choisi,
   avec prévol des nœuds, hash du workflow, réglages autorisés, ID de requête durable,
   statut incertain sans resoumission automatique et collecte locale GLB bornée.
   Réutiliser la logique des profils/reçus textures ; ne pas lui faire déclarer un
   GLB comme une image PNG.
3. **Après mesure sur le PC :** retenir un modèle/version/résolution selon la VRAM,
   le délai, les licences et la qualité des trois objets de test. Garder les dépendances
   CUDA dans l'environnement ComfyUI ou un processus dédié, pas dans Python Blender.
4. **Scènes complexes :** segmentation en objets, puis reconstruction et placement
   explicites. Une façade ou une salle jouable doit rester composée de modules
   éditables avec passages et collisions contrôlés.

La prochaine tâche recommandée est donc **un adaptateur ComfyUI image-vers-GLB
pour les workflows TRELLIS existants, avec profil configurable et reprise**, avant d'ajouter d'autres générateurs.
La qualification utilisera un accessoire fermé, un objet à parties fines et une
façade. Pour chacun : PNG source, workflow/modèle exact, durée/VRAM, GLB brut,
normalisation éventuelle, rapport Asset Doctor, rendu Blender et essai Unreal.
