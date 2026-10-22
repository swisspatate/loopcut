# Comparer les variantes dans une scène commune — v0.30

L'outil prépare une scène de revue Unreal pour le **jeu existant**. Il place 2–8
variantes au même emplacement et n'en affiche qu'une à la fois. Une CameraActor,
deux lumières directionnelles blanches mobiles et une exposition manuelle sont
communes. Les slots de matériaux sont remplacés sur les nouveaux composants,
jamais dans les meshes sources. Il peut comparer des copies de meshes différentes,
à condition de conserver des pivots, unités et échelles compatibles.

Les contrôles réutilisent GameProject, les empreintes de packages/sidecars de
Creative Director, l'inspecteur Unreal des matériaux et le calcul de visée des
caméras. Les tests cloud utilisent des **doubles d'API**, pas Unreal : les chemins
ci-dessous doivent encore être qualifiés dans le vrai éditeur 5.8.

## Préparer le plan

1. Activer Python Editor Script et Editor Scripting Utilities dans le projet.
2. Créer une carte vide **sans contenu de template**, sous
   `/Game/CryptoNyan/ReviewMaps/CompareSkins`. L'enregistrer, puis sauvegarder les
   assets sources et arrêter PIE. Seul WorldSettings est autorisé avant création.
3. Adapter [l'exemple](examples/unreal-comparison.json) aux chemins des vrais meshes
   et matériaux. Le premier élément est la référence. Les overrides utilisent les
   indices de slots lus avec l'inspecteur existant ; une liste vide garde les slots
   du mesh. Même classe pour toutes les variantes : StaticMesh ou SkeletalMesh.
4. Dans PowerShell, hors du projet :

```powershell
$env:PYTHONPATH = 'D:\Dev\loopcut\scripts\addons_core'
python -m cryptonyan_asset_studio.comparison_review plan `
  'D:\CryptoNyanWork\comparison.json' `
  --project 'D:\Games\CryptoNyanRunUnreal' `
  --output 'D:\CryptoNyanWork\comparison-plan.json'
```

La carte `.umap` doit déjà exister localement. Le plan lie le checkout et le
descripteur `.uproject`, les packages sources et leurs sidecars, et les octets du
fichier `.umap` ; il est recalculé à chaque contrôle. Les pointeurs Git LFS sont
refusés. La limite de snapshot est 512 Mio par package/carte, avec le budget
d'inspection existant de 1 Gio pour les assets explicitement sélectionnés.

## Construire et sélectionner dans Unreal

Dans la console Python de **l'éditeur Unreal**, avec la carte prévue ouverte :

```python
import sys
sys.path.insert(0, r'D:\Dev\loopcut\scripts\addons_core')
from cryptonyan_asset_studio import unreal_comparison as comparison

plan = r'D:\CryptoNyanWork\comparison-plan.json'
# Plan seulement, sans importer Unreal ni créer d'acteurs : dossier nouveau.
comparison.create(plan, r'D:\CryptoNyanWork\stage-dry')
# Construire réellement, dans un autre dossier nouveau.
result = comparison.create(plan, r'D:\CryptoNyanWork\stage-001', apply=True)
print(result)
session = r'D:\CryptoNyanWork\stage-001\session.json'

comparison.select(plan, session, 'Neon',
    r'D:\CryptoNyanWork\selection-neon-001.json', apply=True)
```

Les reçus doivent indiquer `created_review_required` et `selected_review_required`.
Tous les fichiers de reçu sont nouveaux. Une carte occupée, PIE actif, des packages
sales, une autre carte ou un autre projet entraînent un refus avant placement.
En cas d'échec après placement, seuls les acteurs créés par l'appel sont retirés ;
le reçu indique les éventuels acteurs restants. Les sources ne sont ni importées,
dupliquées, sauvegardées ni remplacées. La carte n'est jamais sauvegardée par l'outil.

La session reste liée à l'éditeur ouvert. **Ne pas enregistrer ou changer la carte
pendant la comparaison** : les empreintes et acteurs ne correspondraient plus.
Une session en échec est inutilisable. Fermer la carte sans sauvegarder permet de
terminer cet essai ; une autre revue exige un nouveau dossier/session et une carte
vide. Garder un seul utilisateur/script actif sur la scène pendant les opérations.

Piloter manuellement `CN_Compare_Camera` pour voir le cadrage et le post-traitement
communs. L'outil ne change pas automatiquement le viewport actif. Les positions
sont en **mètres dans le repère Unreal**, converties en centimètres ; les rotations
sont `[roll, pitch, yaw]`. Le réglage d'exposition est une compensation EV en mode
manuel, sans exposition physique de caméra : ce n'est pas un EV100 photographique.

## Personnage et pose figée

Pour les variantes SkeletalMesh, `pose: null` demande une pose de référence avec
un mode single-node vide. Pour un échantillon d'animation commun :

```json
"pose": {"animation": "/Game/Animations/Run.Run", "time_s": 0.25}
```

Toutes les variantes et l'AnimSequence doivent utiliser le même Skeleton. Le temps
doit être dans la durée de la séquence. Le composant reçoit des données d'animation
single-node arrêtées à cette position ; simulation de vêtement et dispatch des
notifies sont désactivés sur les nouveaux composants. La relecture contrôle les
données demandées, **pas les transformations évaluées des os**. Vérifier réellement
la pose affichée dans Unreal 5.8 avant toute comparaison. Ce parcours ne reproduit
pas l'Animation Blueprint, les déplacements du personnage ou une simulation Chaos.

## Collecter et comparer des PNG

Capturer manuellement le cadrage de la caméra en PNG LDR, avec des dimensions
constantes et un ratio identique à celui de la caméra (marge d'un pixel). Attendre
la compilation des shaders, le chargement des textures et la stabilisation de
Lumen/TSR après chaque changement. Puis, dans la même console Unreal :

```python
comparison.select(plan, session, 'Base',
    r'D:\CryptoNyanWork\selection-base-001.json', apply=True)
# Prendre maintenant la capture de Base, puis collecter son fichier :
comparison.collect(plan, session, r'D:\CryptoNyanWork\screens\base.png',
    r'D:\CryptoNyanWork\capture-base')
comparison.select(plan, session, 'Neon',
    r'D:\CryptoNyanWork\selection-neon-002.json', apply=True)
# Prendre maintenant la capture de Neon, puis collecter son fichier :
comparison.collect(plan, session, r'D:\CryptoNyanWork\screens\neon.png',
    r'D:\CryptoNyanWork\capture-neon')
```

La collecte vérifie les sources vivantes, tous les acteurs/slots, la caméra, les
lumières, les paramètres de pose et l'unique variante visible. Elle copie les
octets PNG validés, leur SHA-256 et le lien à la session. La provenance reste
`user_supplied_png_not_renderer_verified` : fournir un vieux fichier ou une image
sans rapport reste possible ; l'outil **ne prouve pas l'origine ni la synchronisation
de la capture** et n'exécute aucun screenshot moteur.

Hors de l'éditeur, produire une galerie HTML autonome :

```powershell
python -m cryptonyan_asset_studio.comparison_review compare `
  'D:\CryptoNyanWork\comparison-plan.json' `
  'D:\CryptoNyanWork\capture-base' 'D:\CryptoNyanWork\capture-neon' `
  --output 'D:\CryptoNyanWork\comparison-gallery'
```

Les images sont conservées dans le nouveau dossier. La galerie exige la référence,
des variantes distinctes, la même session/empreinte de réglages et des dimensions
identiques. Elle refuse les images modifiées. PNG : RGB/RGBA 8 bits non entrelacés,
au plus 4096 pixels par dimension et 32 Mio via le validateur existant.

## Limites et validation locale

L'inspecteur relit les slots, chaînes de parents, paramètres et textures exposées.
Les dépendances transitives arbitraires, textures cachées dans des graphes non
paramétrés, fichiers Engine/plugins et tous les réglages du renderer ne sont pas
gelés. Les références directes du registre ne constituent pas un hash récursif de
toutes leurs dépendances. Les assets explicitement sélectionnés sont vérifiés sur
disque, puis les inspections de matériaux sont comparées dans l'éditeur. Le budget
de leur rapport cumulé est de 8 Mio.

Une modification de caméra, lumière, transform, matériau, propriété de pose, tags,
liste d'acteurs ou visibilité est refusée. Un switch interrompu tente de rétablir
la variante précédente. Il n'y a ni benchmark GPU, adoption d'assets, comparaison
animée continue, assemblage de plusieurs vêtements sur un personnage ou preuve
photométrique entre machines. Les temporisations du renderer, LOD, Nanite, shaders,
post-process d'assets, animation évaluée et performances restent à qualifier sur
le PC. Voir la [checklist](local-pc-checklist.md).

Références Epic consultées pour les API, sans copie de code tiers :
[SkeletalMeshComponent](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/SkeletalMeshComponent),
[Actor](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/Actor),
[index des données single-node](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/genindex-S).
