# Versions visuelles — v0.25

Conserver plusieurs candidats **terminés par Image Workshop**, comparer leurs
références et rendus, retenir une version puis récupérer une copie indépendante.
Le panneau est dans **Vue 3D → CryptoNyan → Versions visuelles**, après
l'enregistrement habituel de `cryptonyan_asset_studio`.

Ce premier historique porte sur les candidats du Workshop : ce n'est pas un
historique universel des scènes Blender, des rigs ou des assets Unreal. Il ne
restaure pas le jeu et ne charge pas de scène dans Blender. L'implémentation est
indépendante ; aucun code de checkpoint Mixar ni service Mixar n'est utilisé.

## Parcours dans Blender

1. Créer un historique par asset, par exemple `D:\CryptoNyanWork\versions\temple`.
   Renseigner le dossier du **projet Unreal existant**, si concerné : il devient
   une limite de destination interdisant d'y restaurer/exporter depuis cet historique.
2. Préparer puis construire un candidat avec [Image Workshop](image-workshop.md).
   Choisir son dossier contenant `operation.json`, `inputs`, `candidate.blend`,
   `candidate.glb`, `render.png` et les rapports.
3. Choisir un identifiant unique (`v01`) et une description puis **Archiver**.
   Pour conserver la provenance du tableau, charger/sélectionner sa référence dans
   le panneau voisin puis **Archiver avec la référence sélectionnée**. Image,
   recette et cible doivent encore correspondre ; l'historique doit déclarer le
   même projet si le tableau en déclare un. Cette liaison est facultative et explicite.
4. Construire un deuxième candidat dans un autre dossier, l'archiver sous `v02`.
   **Comparer les rendus** crée un nouveau HTML autonome : référence/rendu de chaque
   version, recettes, triangles et champs modifiés. Ouvrir le fichier dans un navigateur.
5. **Retenir cette version** enregistre seulement la sélection dans l'historique.
   **Restaurer une copie** exige un nouveau dossier, par exemple
   `D:\CryptoNyanWork\review\temple-v01`. Ouvrir ensuite cette copie manuellement
   pour inspection ; l'outil ne remplace aucun fichier existant.

Recharger l'historique après une modification depuis un autre processus. Une
révision périmée est refusée au lieu d'écraser la sélection ou les nouvelles versions.
Le panneau liste les descriptions ; les rendus côte à côte sont dans le HTML.
Les opérations de copie/vérification sont synchrones et peuvent prendre du temps
pour de gros candidats ; aucune génération n'est lancée par ce panneau.

## CLI pour un agent ou PowerShell

Depuis la racine du fork, avec Python autonome 3.11+ :

```powershell
$env:PYTHONPATH = "$PWD\scripts\addons_core"
python -m cryptonyan_asset_studio.visual_versions create D:\CryptoNyanWork\versions\temple --id temple --title "Temple de glace" --project D:\Jeux\CryptoNyanRunUnreal
python -m cryptonyan_asset_studio.visual_versions archive D:\CryptoNyanWork\versions\temple --revision 0 --version v01 --label "Silhouette initiale" --attempt D:\CryptoNyanWork\attempts\temple-01
python -m cryptonyan_asset_studio.visual_versions archive D:\CryptoNyanWork\versions\temple --revision 1 --version v02 --label "Toit affiné" --attempt D:\CryptoNyanWork\attempts\temple-02
python -m cryptonyan_asset_studio.visual_versions compare D:\CryptoNyanWork\versions\temple --left v01 --right v02 --output D:\CryptoNyanWork\temple-comparison.html
python -m cryptonyan_asset_studio.visual_versions select D:\CryptoNyanWork\versions\temple --revision 2 --version v01
python -m cryptonyan_asset_studio.visual_versions restore D:\CryptoNyanWork\versions\temple --version v01 --output D:\CryptoNyanWork\review\temple-v01
python -m cryptonyan_asset_studio.visual_versions check D:\CryptoNyanWork\versions\temple --version v01
```

`archive` accepte aussi `--board D:\CryptoNyanWork\references\temple --reference front`.
`list DOSSIER` lit l'index ; `check` vérifie réellement les fichiers de la version.
Les réponses sont du JSON. Les outils MCP de tableaux restent disponibles ; cette
version n'ajoute pas d'outil MCP de mutation d'historique. Un agent ayant accès à
la CLI peut utiliser les commandes ci-dessus.

## Intégrité et limites

- Copies indépendantes des entrées et des six livrables, empreintes SHA-256,
  identité de recette et vérification GLB/rapport réutilisant Loopcut. Les logs et
  autres fichiers non déclarés ne sont pas archivés. Le `.blend` est copié et
  haché, jamais exécuté ni interprété pour vérifier son contenu.
- Maximum 32 versions, 512 Mio par candidat, 2 Gio de données de candidats par
  historique ; métadonnées bornées séparément. Pas de suppression ni de déduplication.
- Verrou d'écriture et révision attendue ; index publié atomiquement après copie
  vérifiée. Un arrêt entre publication du dossier et de l'index peut laisser un
  dossier non référencé dans `versions`. Il n'est ni listé ni restaurable : après
  inspection manuelle, utiliser un nouvel identifiant. Pas de réparation automatique.
- Une restauration échouée retire uniquement le nouveau dossier créé par l'opération.
  Une destination existante, dans l'historique ou dans le projet déclaré est refusée.
  Déclarer le projet est nécessaire pour protéger cette limite ; l'outil ne connaît
  pas les projets omis. Utiliser un dossier de travail privé, séparé du jeu.
- La provenance du tableau est un instantané au moment de l'archivage, pas une
  autorisation permanente d'appliquer le candidat à un asset devenu différent.
  Le reçu de restauration la conserve. Aucune application au jeu n'est effectuée.
- SHA-256 détecte une modification accidentelle ; ce n'est pas une signature contre
  quelqu'un qui réécrit à la fois l'index et tous les fichiers.
- Une caméra ou une référence différente déclenche un avertissement. Une caméra
  identique ne garantit pas un rendu comparable entre versions de Blender, moteurs,
  couleurs ou éclairages : ces paramètres d'exécution ne sont pas tous capturés par
  l'ancien reçu Workshop. Aucun score de fidélité ou de qualité n'est calculé.
- Windows avec affichage, vraies sorties TRELLIS, déformations de rigs et import
  dans Unreal 5.8 nécessitent la [validation locale](local-pc-checklist.md).
