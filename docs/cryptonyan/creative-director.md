# Effets, cutscenes et architecture pour le jeu existant — v0.40

Le Director produit des candidats Unreal à partir de recettes explicites utilisant
tes assets existants. Les trois premiers parcours restent indépendants du plugin ;
le nouveau [surface_feedback](surface-feedback.md) exige CryptoNyanRuntime 0.4 compilé.
Le plan se prépare hors éditeur, puis l'adaptateur réalise les opérations dans Unreal.
**Les tests cloud utilisent des doubles d'API : l'exécution, le rendu et le gameplay
sur Unreal 5.8 restent à valider localement.** Aucun asset du jeu privé n'a été modifié.

| Recette | Opération implémentée | Résultat |
|---|---|---|
| `surface_feedback` | Profil sons/Niagara par PhysicalMaterial et copie d’animation avec contacts | Data Asset et AnimSequence ; composant à brancher sur une copie du Character |
| `effects` | Duplication d'une AnimSequence et ajout de `AnimNotify_PlayNiagaraEffect` | `AN_Directed` avec une piste dédiée ; originaux et AnimBlueprint conservés |
| `cinematic` | Création de caméras spawnables, pistes de transform et Camera Cuts | Nouvel asset `LS_Directed`, sans lecture automatique ni modification de la carte |
| `architecture` | Placement de rangées de StaticMeshActors depuis un catalogue de meshes | Acteurs dans une carte de revue vide, à examiner puis sauvegarder manuellement |

## Préparer un plan

Les [exemples JSON](examples/) utilisent des **chemins et noms fictifs**.
Les remplacer par les assets du projet, les vrais os/sockets et les durées mesurées.
`reviewed: true` dans l'exemple d'effets est une déclaration à renseigner après revue
de tes timings ; l'exemple ne constitue aucune validation de ton animation.

Dans PowerShell, depuis Loopcut :

```powershell
$env:PYTHONPATH = "$PWD\scripts\addons_core"
python -m cryptonyan_asset_studio.creative_director `
  D:\Review\directed-effects.json --project D:\CryptoNyanRunUnreal `
  --output D:\Review\effects-plan.json

python -m cryptonyan_asset_studio.unreal_director `
  D:\Review\effects-plan.json --report D:\Review\effects-dry-run.json
```

Créer `D:\Review` au préalable, en dehors du projet. Les fichiers de sortie doivent
être nouveaux. Remplacer la recette par `directed-cinematic.json` ou
`directed-architecture.json` pour les deux autres parcours. Le plan contient les
opérations calculées, les hashes des `.uasset` sources et de leurs sidecars `.uexp` /
`.ubulk`, ainsi que l'identité du checkout/projet. Télécharger Git LFS avant de planifier.
Les dépendances transitives, modèles Niagara et matériaux indirects ne sont pas tous
épinglés : le plan ne certifie pas leur contenu ou leur coût GPU.

Un plan modifié ou une source changée est rejeté à l'exécution : refaire le plan après
la modification volontaire. Ces fichiers restent locaux car ils contiennent des chemins
de ton PC. Le dry-run valide le plan et les hashes, **pas** les classes Unreal ou le rendu.
Les agents peuvent appeler ces CLI et fonctions ; aucun nouvel outil MCP n'est ajouté.

## Exécuter dans l'éditeur Unreal

Ouvrir le bon projet sous Unreal 5.8. Activer Python Editor Script Plugin,
Editor Scripting Utilities, Sequencer Scripting et Niagara selon le parcours ; les
classes de Level Sequence Editor et AnimationLibrary doivent être accessibles dans
le Python de l'éditeur. Sauvegarder les modifications de contenu en cours : le prévol
refuse les packages de contenu dirty. Utiliser un seul éditeur/opérateur pendant l'exécution.

Dans la console Python Unreal, ou un script Python lancé depuis l'éditeur :

```python
import sys
sys.path.insert(0, r"D:\loopcut\scripts\addons_core")
from cryptonyan_asset_studio.unreal_director import execute
result = execute(
    r"D:\Review\effects-plan.json",
    r"D:\Review\effects-result.json",
    apply=True,
)
print(result)
```

`apply=True` réalise les créations demandées. Il ne démarre pas PIE, ne change pas de
carte, ne sauvegarde pas la carte et ne branche pas le candidat dans ton AnimBlueprint.
Le dossier `/Game/CryptoNyan/DirectedReviews/<Id>` doit être nouveau : pas de réutilisation
d'un dossier partiel ou terminé. Le reçu distingue `planned`, `created_review_required`,
`placed_review_required` et `failed`, avec assets créés/sauvegardés et étape d'échec.
`engine_validated: false` rappelle qu'une création d'asset ne valide pas son gameplay.

En cas d'échec, les assets candidats déjà créés sont conservés et listés pour inspection ;
aucun nettoyage d'asset ou remplacement automatique. Pour l'architecture, seuls les
acteurs créés par cet appel font l'objet d'une tentative de suppression. Le reçu donne
`removed_actors` et `remaining_actors` si le rollback échoue. La carte peut rester dirty.
Après un crash brutal, examiner le dossier et la carte avant toute nouvelle tentative :
ce système n'est pas une transaction atomique multi-assets ni une reprise automatique.

## Effets synchronisés

Une recette associe un temps en secondes, un os/socket existant et un système Niagara
déjà créé. Types descriptifs disponibles : `contact`, `dash`, `landing`, `impact`, `cast`.
Le type sert à organiser la recette ; le comportement visuel dépend du système Niagara.
Les instants doivent appartenir à `[0, durée)` pour éviter un événement placé exactement
sur la fin d'une boucle. Maximum 64 événements ; les doublons de même instant/socket/
système sont refusés. Il ne s'agit pas d'un filtre anti-doublon en runtime pour le blending.

Le prévol vérifie la durée, le Skeleton commun de l'animation et du mesh de prévisualisation,
les classes des assets et l'existence des sockets/os. Il duplique l'animation, conserve ses
notifies et ajoute la piste `CN_DirectedEffects`. Une animation possédant déjà cette piste
est refusée pour éviter d'empiler la même génération. Les notifies des autres pistes restent
à examiner pour des effets éventuellement redondants.

`attached: true` suit le socket ; `false` convient par exemple à une poussière laissée
au sol. Les offsets sont saisis en mètres dans le repère utilisé par le notify puis convertis
en centimètres. L'échelle est absolue. Le notify conserve sa rotation par défaut. Les
effets ne se déclenchent pas dans l'éditeur d'animation par défaut (`should_fire_in_editor`
est désactivé) : l'activer sur la **copie** pour la prévisualisation, ou tester en PIE.
Utiliser des Niagara one-shot à durée bornée : l'outil n'ajoute pas d'arrêt à un système
infini et ne génère pas de nouveau graphe Niagara.

### Importer les appuis d'Animation Doctor

Créer une recette `effects` avec `events: []`, une durée égale à la trace, puis un fichier
de correspondance, par exemple :

```json
[
  {"contact_id": "contact-000", "socket": "PawL",
   "niagara": "/Game/Effects/NS_Dust.NS_Dust", "attached": false,
   "offset_m": [0, 0, 0], "scale": [1, 1, 1], "reviewed": true}
]
```

```powershell
python -m cryptonyan_asset_studio.creative_director `
  D:\Review\effects-empty.json --project D:\CryptoNyanRunUnreal `
  --trace D:\AnimationReview\run-001\trace.json `
  --settings D:\AnimationReview\settings.json `
  --contact-bindings D:\Review\contacts.json --output D:\Review\contacts-plan.json
```

`settings.json` contient uniquement l'objet `settings` de la capture Blender.
Le module **recalcule l'audit depuis la trace**, puis importe les contacts mesurés
`within_threshold`. Il refuse les appuis glissants/non évalués ; modifier `events.json`
pour lui donner `approved: true` ne contourne pas ce parcours. Les correspondances
Blender→Unreal et la même durée ne prouvent pas que les deux clips sont identiques :
vérifier le retargeting et les appuis dans le jeu. Pour une animation sur place sans
trajectoire mondiale, utiliser des timings revus manuellement, sans présenter le résultat
comme une mesure de glissement réussie.

## Cutscenes réutilisables

Chaque plan contient 2–36000 frames et des clés sur sa première et sa dernière frame
visible. Les plans sont enchaînés sans trou ; leurs fins sont exclusives. Les clés se
placent au framerate d'affichage (1–120 fps), pas dans les ticks internes de Sequencer.
Maximum 16 plans, 128 clés par plan, dix minutes au total.

Positions : **mètres dans le repère Unreal**, X avant, Y droite, Z haut. Rotations :
`[roll, pitch, yaw]` en degrés. Ce n'est pas une conversion automatique de coordonnées
Blender. L'interpolation est linéaire ; les angles successifs sont déroulés pour éviter
qu'un passage de 179° à −179° fasse presque un tour complet. Les tours intentionnels
doivent utiliser des clés intermédiaires espacées de moins de 180°.

Le résultat possède des caméras spawnables, des pistes de transform et de Camera Cuts.
La lentille, le focus et l'exposition sont ceux du CineCameraActor par défaut : les ajuster
dans Sequencer. Aucun personnage, animation, son, événement gameplay ou rendu vidéo
n'est ajouté. Le déclenchement en jeu, le skip, la reprise des contrôles, les sous-séquences
et Movie Render Queue restent à intégrer. Commencer par une intro de niveau de six secondes.

## Architecture avec les meshes existants

`modules` mappe des rôles réutilisables vers tes Static Meshes. Une rangée définit son
origine, son pas de répétition, son nombre, son yaw et son échelle. L'ancre et le yaw
globaux déplacent/rotatent tout le plan ; changer le catalogue permet de réutiliser une
disposition dans un jardin, une mine ou une ville. Ajouter des rangées à différentes
hauteurs pour plusieurs étages. Maximum 32 meshes distincts, 64 rangées, 256 acteurs.

Créer puis ouvrir une **carte vide** à l'emplacement `target_level`, sous
`/Game/CryptoNyan/ReviewMaps/`. Seul WorldSettings est autorisé au départ. Les pivots
et dimensions doivent correspondre aux pas de la recette ; les origines exactement
superposées sont refusées. Les matériaux et collisions restent ceux des meshes.
Les acteurs sont placés individuellement, sans HISM, PCG, socket snapping ni fusion.
Les intersections réelles, la navigation, le budget de draw calls et les collisions ne
sont pas validés. Après revue, sauvegarder la carte ou transférer les acteurs sélectionnés
vers une copie du niveau existant. Aucun niveau de production n'est modifié par l'outil.

## Tests et validations encore locales

```powershell
python -m unittest discover -s loopcut/tests -p test_cryptonyan_director.py -v
```

Ces tests vérifient la logique, les gardes, les conversions, le protocole éditeur et les
CLI ; ils ne compilent ni ne lancent Unreal. Utiliser la [checklist PC](local-pc-checklist.md)
pour tester les vrais notifies, le rendu Sequencer et les modules de décor.
Le [lecteur AnimSequence](rig-and-unreal-animation.md) et les [réparations de poids](rig-repair.md)
complètent ces parcours. La v0.40 ajoute le choix de sons/effets par surface dans un
[composant dédié](surface-feedback.md), avec des limites précises. L'évaluation de
l'AnimBlueprint en PIE et les graphes Niagara paramétrés restent à développer.

API de référence consultées : [AnimationLibrary](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/AnimationLibrary?application_version=5.7),
[AnimNotify_PlayNiagaraEffect](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/AnimNotify_PlayNiagaraEffect),
[LevelSequenceEditorSubsystem](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/LevelSequenceEditorSubsystem?application_version=5.7),
[MovieSceneSequenceExtensions](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/MovieSceneSequenceExtensions?application_version=5.7),
[canaux Double](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/MovieSceneScriptingDoubleChannel?application_version=5.5).
Les signatures documentées ne remplacent pas l'essai sur ton installation 5.8.
