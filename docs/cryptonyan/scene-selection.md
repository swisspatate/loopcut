# Contexte de sélection Blender — v0.27

Donner à l'agent une description de ce que tu veux améliorer : objets sélectionnés,
transformations, UV, matériaux/images, rig et canaux d'animation. Une capture du
viewport peut accompagner cet instantané. L'agent le lit via la bibliothèque de
références déjà configurée ; aucune nouvelle connexion n'est nécessaire.

## Exporter depuis Blender

1. Enregistrer l'extension CryptoNyan et charger son profil de connexion habituel.
   Le champ `reference_root` doit désigner une bibliothèque hors du projet, par
   exemple `D:\CryptoNyanWork\references`.
2. Passer en mode Objet et sélectionner entre 1 et 32 objets. Choisir aussi le rig
   si tu veux son action et ses canaux ; un mesh indique déjà l'armature trouvée et
   les noms de ses os.
3. Ouvrir **Vue 3D → CryptoNyan → Contexte de sélection pour l'agent**. Laisser la
   bibliothèque vide pour utiliser celle du profil, ou renseigner explicitement le
   même dossier. Choisir un nouvel identifiant, par exemple `cat-run-01`.
4. **Exporter les informations** crée uniquement les métadonnées.
   **Exporter avec le viewport** réutilise `loopcut.tools.capture_viewport` avec
   l'angle `user` : c'est la vue 3D actuelle, avec les éléments qui y sont visibles.
   La capture peut donc contenir d'autres objets que la sélection décrite.
5. Reconnecter Claude/Codex après la mise à jour du serveur MCP pour recevoir les
   nouveaux outils. Leur lecture ne déclenche ni capture ni modification de scène.

L'instantané est placé sous `reference_root/scene-contexts/cat-run-01` avec
`context.json` et éventuellement `view.png`. Le dossier doit être nouveau ; pour
actualiser une sélection, exporter un nouvel identifiant. La date et la frame
figurent dans les données. L'instantané ne se synchronise pas avec les modifications
ultérieures de la scène.

## Outils MCP disponibles

| Outil | Fonction |
| --- | --- |
| `reference_scene_list` | Liste les instantanés exportés dans la bibliothèque configurée. |
| `reference_scene_read(snapshot_id)` | Lit les métadonnées et vérifie leur identité ainsi que l'image éventuelle. |
| `reference_scene_image(snapshot_id)` | Retourne l'image comme contenu visuel MCP, dans la limite de 2 Mio. |

Exemple de demande à l'agent :

> Lis `cat-run-01` et sa capture. Propose une variante de tissu en conservant le rig,
> les UV et la silhouette. Prépare les modifications dans une copie à examiner.

Les noms et textes de scène sont des données, pas des instructions exécutables.
L'export n'accorde pas un contrôle de la scène en direct et ne remplace pas les
empreintes d'assets du projet Unreal. Les agents utilisent ensuite les missions,
profils ComfyUI et copies de revue existants selon le travail demandé.

## Contenu et limites

- Résumés d'objets réutilisés de Loopcut : transformations locales, visibilité,
  bornes, mesh de base et noms des matériaux/modifiers. Une matrice mondiale est
  ajoutée. Les coordonnées restent dans les axes/unités Blender ; utiliser
  `unit_scale_m` pour obtenir des mètres. Le mesh évalué final n'est pas exporté.
- Noms des UV, slots, types de nœuds, noms/dimensions/espaces couleur des images et
  état packed. Les graphes complets et les pixels des textures ne sont pas exportés.
- Armature trouvée, noms d'os et mode de pose. Pas d'audit de poids/déformation :
  les Rig/Animation Doctors existants restent nécessaires.
- Action de chaque objet sélectionné, nombre de F-curves et liste bornée des
  chemins animés. Le helper Loopcut gère les actions classiques et à slots.
- Maximum 16 slots, 32 modifiers, 8 UV et 512 os par objet ; 256 nœuds et 32 images
  résumées par matériau ; 16 384 F-curves lues, avec au plus 64 chemins distincts
  affichés. Les sélections trop grandes sont refusées explicitement.
- Métadonnées limitées à 1 Mio, image à 8 Mio, bibliothèque lisible jusqu'à 64
  instantanés. Le nom du fichier Blender et son état saved/dirty sont indiqués ;
  les données non enregistrées ne sont pas écrites dans le `.blend` source.
- La capture GPU exige Blender avec affichage et un viewport 3D disponible. Elle
  utilise le mécanisme natif qui rétablit ses réglages de vue ; le cloud sans
  affichage valide l'export réel de métadonnées et le raccord d'API, pas cette capture.
- `scene-contexts` est un sous-dossier réservé de la bibliothèque ; ne pas y créer
  un tableau portant le même identifiant.

Vérification sans Blender :

```powershell
$env:PYTHONPATH = "$PWD\scripts\addons_core"
python -m cryptonyan_asset_studio.scene_selection list D:\CryptoNyanWork\references
python -m cryptonyan_asset_studio.scene_selection check D:\CryptoNyanWork\references\scene-contexts\cat-run-01
```

Les captures peuvent servir de référence aux [masques sur image](mask-paint.md).
Pour qualifier tes données réelles : [checklist PC](local-pc-checklist.md).
