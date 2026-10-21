# Corrections des poids sur une copie — v0.19

Rig Doctor peut maintenant préparer et appliquer des corrections **sur un nouveau
fichier Blender**, puis rouvrir ce fichier dans un second processus pour le vérifier.
Le personnage original et le dossier d'audit restent les références de départ.

Le périmètre est précis : normaliser les poids des os déformants et conserver les
influences principales selon un budget choisi. L'outil ne choisit pas les os des
sommets sans poids, ne reconstruit pas le rig et ne remplace pas le personnage Unreal.
Il réutilise le lecteur Rig Doctor et le superviseur de processus existants. Les agents
locaux peuvent lancer la CLI ; aucun nouvel outil MCP n'est ajouté.

## 1. Auditer une copie de travail avec la v0.19

Suivre le [guide Rig Doctor](rig-and-unreal-animation.md) pour produire un dossier neuf
contenant `source.blend`, `weights.json` et `audit.json`. Refaire les captures v0.18 :
la v0.19 ajoute l'état des verrous, le nombre d'utilisateurs du mesh, les overrides
et le mode de l'objet, nécessaires à la correction.

Les meshes sélectionnés doivent être locaux, en Object Mode et avoir un seul utilisateur
de leurs données. Les données partagées et overrides sont refusés. Préparer leur copie
indépendante dans Blender si nécessaire, puis refaire l'audit. Les contraintes de
liaison Armature de Rig Doctor restent applicables.

## 2. Préparer et examiner le plan

Copier [rig-repair-policy.json](examples/rig-repair-policy.json) hors du dossier d'audit :

```json
{"max_influences": 4, "max_removed_fraction": 0.25}
```

`max_influences` est un budget de 1 à 32, pas une limite universelle d'Unreal.
`max_removed_fraction` limite la proportion de la somme des poids déformants qui
serait supprimée avant renormalisation, entre 0 et 0,5. Par exemple, cinq poids égaux
réduits à quatre retirent 20 % ; le plafond de 25 % accepte cette proposition.
Cette proportion n'est pas une mesure de déformation visuelle.

```powershell
$env:PYTHONPATH = "C:\Dev\loopcut\scripts\addons_core"
python -m cryptonyan_asset_studio.rig_repair plan `
  C:\CryptoNyanReviews\rig-audit-001 `
  --policy C:\CryptoNyanReviews\rig-repair-policy.json `
  --output C:\CryptoNyanReviews\rig-plan-001.json
```

Le JSON contient les affectations avant/après de chaque sommet modifié, la fraction
supprimée, les constats prévus après correction et les cas non modifiés à examiner.
Il est lié aux hashes du `.blend`, des poids et du rapport. Toute modification du
plan ou de ses entrées est refusée à l'exécution : générer un nouveau plan pour
changer la politique. Le plan doit tenir dans 32 MiB ; réduire la sélection sinon.

Règles de calcul :

- Les influences supérieures au `weight_epsilon` de l'audit sont triées par poids
  décroissant ; les égalités sont départagées par nom d'os.
- Les influences retenues sont renormalisées à une somme de 1. Le plafond de retrait
  prend aussi en compte les petits poids écartés sous `weight_epsilon`.
- Les groupes sans os correspondant et les os non déformants conservent leurs poids.
- Un sommet avec poids invalide, sans influence significative, avec une affectation
  déformante verrouillée ou dépassant le plafond de retrait reste entier et inchangé.
  Ces cas figurent dans `manual_review`, avec compte total et au plus 100 indices
  par mesh/motif. Un verrou ne signifie pas nécessairement un défaut à corriger.

## 3. Prévisualiser, puis créer le candidat

La commande suivante vérifie le plan sans lancer Blender :

```powershell
python -m cryptonyan_asset_studio.rig_repair execute `
  C:\CryptoNyanReviews\rig-plan-001.json --output C:\CryptoNyanReviews\rig-dry-001
```

Après examen du plan, créer le candidat avec un autre dossier neuf :

```powershell
python -m cryptonyan_asset_studio.rig_repair execute `
  C:\CryptoNyanReviews\rig-plan-001.json --apply `
  --blender "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe" `
  --output C:\CryptoNyanReviews\rig-candidate-001
```

Les deux processus Blender démarrent avec paramètres usine et scripts automatiques
désactivés. Le premier compare les poids lus au plan, applique les affectations et
sauvegarde `candidate.blend`. Le second rouvre ce candidat et compare **tous les poids
sélectionnés**, y compris les groupes auxiliaires, avec une tolérance absolue de 1e-6
pour le stockage float32. Le superviseur revérifie les hashes des entrées et du candidat.
Le budget total des deux processus est 120 s, configurable avec `--timeout` jusqu'à 600 s.

La signature de protection couvre les coordonnées, arêtes, faces et indices de
matériaux, UV, coordonnées/valeurs des shape keys, groupes/verrous, matrices de repos
et matrices de base du rig et des objets sélectionnés. Elle est vérifiée avant/après
écriture et à la réouverture. Elle ne certifie pas toutes les propriétés Blender ni
la déformation évaluée. Budgets supplémentaires : 100 000 faces, 500 000 loops et huit
UV layers par mesh, 64 shape keys et deux millions d'éléments de signature au total.

Les fichiers externes non empaquetés et bibliothèques liées sont refusés pour éviter
de casser des chemins relatifs lors de la sauvegarde ailleurs. Préparer un `.blend`
autonome dans Blender ; aucun téléchargement ni empaquetage automatique n'est effectué.

Sorties principales : `result.json`, `candidate.blend`, `verified-weights.json`,
`audit.json`, ainsi que la copie source, le plan et les dossiers de travail.
`candidate_created_review_required` signifie que les vérifications numériques passent,
pas que le personnage est visuellement validé. Les sommets non corrigés restent signalés.
Si aucune opération n'est proposée, le statut est `no_automatic_changes`, sans candidat.
En cas d'échec, le reçu indique `failed` et ne publie aucun candidat validé ; les fichiers
partiels sont conservés pour diagnostic, sans réutilisation du dossier.

Codes de sortie : `0` commande réussie sans cas restant à examiner, `1` cas manuels ou
constats restants, `2` erreur. La préparation d'un plan valide retourne `0` même s'il
contient des cas manuels : les examiner dans son résumé. Les sorties existantes sont
refusées, et aucune sortie ne peut être créée dans le dossier d'audit source.

## Acceptation sur ton personnage

Ouvrir le candidat séparément avec les scripts automatiques désactivés. Comparer la
source et le candidat dans Weight Paint, puis jouer les animations et tester les poses
extrêmes, IK, shape keys et accessoires. Contrôler particulièrement les sommets dont
une influence a été supprimée. Relever les éventuelles régressions visuelles même si
l'audit numérique est meilleur.

L'import dans Unreal reste une étape manuelle sur un asset candidat : vérifier squelette,
influences réellement importées, matériaux, animations et déformations avant adoption.
Les tests cloud emploient une fixture, pas le personnage privé du jeu. Tous les essais
Windows et Unreal restants figurent dans la [checklist PC](local-pc-checklist.md).

```powershell
$env:LOOPCUT_BLENDER = "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe"
python -m unittest discover -s loopcut/tests -p test_cryptonyan_rig_repair.py -v
```
