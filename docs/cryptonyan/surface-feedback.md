# Sons et effets de déplacement par surface — v0.40

Cette première extension relie les contacts du rig existant aux bruitages et à
Niagara. Elle réutilise les plans Creative Director, les empreintes des packages,
la file Studio et les scripts de transfert vers l'éditeur. Le plugin runtime
passe à **0.4.0**. Aucun rig, contrôleur ou Animation Blueprint n'est remplacé.

Deux parties sont implémentées :

- **Éditeur** : une recette `surface_feedback` crée un Data Asset de configuration
  et une copie d'AnimSequence avec des notifies de contact explicitement datés.
- **Jeu solo** : un composant ajouté à une copie du Character trace le sol sous
  les os/sockets déclarés, choisit la variante pour le PhysicalMaterial touché,
  puis émet un son et/ou un Niagara à cet endroit. La vitesse règle volume et
  taille ; un tirage propre au composant règle la variante sonore et le pitch.

**Unreal n'est pas installé dans le cloud.** Les tests Python utilisent des doubles
d'API ; seules les règles C++ indépendantes du moteur sont compilées ici. Les deux
tests d'automation Unreal sont fournis pour ton PC, mais n'ont pas été exécutés ici.
Compilation UHT/Unreal, collisions, audio, notifies, PIE et packaging restent locaux.

## 1. Compiler et charger le plugin

Utiliser UE 5.8 et le toolchain C++ Windows correspondant. Le plugin est sous
`integrations/unreal/CryptoNyanRuntime`. Mettre à jour sa copie dans
`<projet de validation>/Plugins/CryptoNyanRuntime`, fermer l'éditeur et compiler
la cible Editor du projet. Ne pas copier un plugin dans le dépôt Loopcut lui-même.
Ne pas conserver plusieurs installations actives du même module dans le projet
et le moteur. Les fonctions antérieures du plugin restent présentes.

Pour vérifier séparément la compilation du plugin, adapter ces chemins :

```powershell
& 'D:\Epic\UE_5.8\Engine\Build\BatchFiles\RunUAT.bat' BuildPlugin `
  -Plugin='D:\Dev\loopcut\integrations\unreal\CryptoNyanRuntime\CryptoNyanRuntime.uplugin' `
  -Package='D:\CryptoNyanBuilds\FeedbackPlugin-040' -TargetPlatforms=Win64
```

Le dossier de package doit être neuf et distinct du projet et des sources.
BuildPlugin compile le code ; il ne prouve pas son fonctionnement en jeu.
Activer Niagara, Python Editor Script Plugin et les API AnimationLibrary utilisées
par le [Director](creative-director.md). `PhysicsCore` est ajouté aux dépendances.

## 2. Préparer les vrais inputs

Partir de [surface-feedback.json](examples/surface-feedback.json). **Tous les chemins,
les noms `ExampleFootA`… et les timings de cet exemple sont fictifs.** Les remplacer
par ceux du mesh, du rig et de l'AnimSequence du jeu. `reviewed: true` est une
déclaration de revue des instants, pas une mesure ou une approbation authentifiée.
Cette version ne déduit pas automatiquement les appuis d'un clip ou d'une image.

La recette contient :

| Champ | Utilisation |
| --- | --- |
| `animation`, `preview_mesh`, `duration_s` | Clip existant, mesh exact et durée mesurée ; Skeleton identique requis |
| `foot_sockets` | 1–8 vrais noms d'os/sockets, distincts sans tenir compte de la casse |
| `events` | 1–64 contacts avec ID, seconde dans `[0, durée)`, socket mappé et revue déclarée |
| `cues` | 1–32 correspondances uniques entre `contact`, `jump` ou `landing` et PhysicalMaterial |
| `physical_material` dans une cue | Asset exact ; `null` est le fallback explicite de cet événement |
| `sounds` | 0–8 SoundWaves distinctes, mono, non bouclées et courtes |
| `niagara` | NiagaraSystem existant ou `null` ; chaque cue exige au moins son ou effet |
| `attenuation` | SoundAttenuation existante, obligatoire dès qu'un son est utilisé |
| `volume`, `pitch`, `effect_scale` | Paires min/max bornées ; l'atténuation et les assets gardent leurs réglages |
| `reference_speed_cm_s` | Vitesse pour atteindre l'intensité maximale de cette cue |
| `settings` | Dimensions du rayon, délais, seuil de vitesse et budgets d'émission |

Les SoundWaves doivent déjà être importées : pas de synthèse, d'import WAV ni de
workflow audio ComfyUI dans cette version. SoundCue, MetaSoundSource, stéréo et
boucles sont exclus de ce premier adaptateur. La durée du WAV doit être comprise
entre 0,001 s et `hard_stop_seconds * pitch_min`, afin de tenir même au pitch lent.
Un asset SoundAttenuation déclaré ne certifie pas sa spatialisation : la régler et
l'écouter localement. Un Niagara peut boucler ; le composant le détruit à la limite
de temps, sans modifier son graphe ni inventer de paramètres utilisateur.

Les réglages acceptent : trace au-dessus 1–100 cm, en dessous 1–200 cm, délais
0,04–1 s, vitesse de contact minimale 0–1 000 cm/s, durée maximale 0,05–5 s,
1–16 sons et 1–16 effets actifs. Volume 0–1, pitch 0,5–2, échelle 0,01–3,
vitesse de référence 1–5 000 cm/s. Limite de 128 assets explicites et budgets
existants de packages/sidecars. Aucune licence, qualité artistique ou mesure de
sonie n'est déduite des métadonnées.

## 3. Depuis l'agent ou la CLI

Demande possible : « Prépare les sons de pas de ce personnage selon le sol, en
utilisant ces animations, sons et matériaux physiques. » L'agent doit découvrir les
vrais assets et timings. `studio_guide` avec `capability=creative_director` retourne
`surface_feedback_schema`, la structure complète. Les contraintes entre champs
(durée, sockets, paires ordonnées, classes) sont encore vérifiées par le backend.

Soumettre `director_plan` via `studio_submit`, avec `arguments={"recipe": ...}` et
un ID stable. Lire le résultat et les artefacts ; utiliser son vrai handle de plan
pour `unreal_handoff` avec `kind=director_review`. Ce script reste inerte tant qu'il
n'est pas exécuté dans la bonne session Unreal locale. Les outils MCP n'ont pas
été multipliés et les anciens profils de connexion restent compatibles.

La CLI réutilise aussi les modules existants :

```powershell
$env:PYTHONPATH = (Resolve-Path .\scripts\addons_core).Path
py -3.13 -m cryptonyan_asset_studio.creative_director `
  'D:\Review\surface-feedback.json' --project 'D:\Games\CryptoNyanRunUnreal' `
  --output 'D:\Review\surface-plan.json'
py -3.13 -m cryptonyan_asset_studio.unreal_director `
  'D:\Review\surface-plan.json' --report 'D:\Review\surface-dry-run.json'
```

Puis, dans le Python de l'éditeur approprié, après avoir sauvegardé le contenu en
attente et avec un seul opérateur éditeur :

```python
import sys
sys.path.insert(0, r"D:\Dev\loopcut\scripts\addons_core")
from cryptonyan_asset_studio.unreal_director import execute
result = execute(r"D:\Review\surface-plan.json",
                 r"D:\Review\surface-result.json", apply=True)
print(result)
```

Le dossier `/Game/CryptoNyan/DirectedReviews/<Id>` doit être nouveau. Résultats :
`DA_SurfaceFeedback` et `AN_SurfaceFeedback`, avec une piste `CN_SurfaceContacts`.
Les notifies existants sont conservés et leur nombre est rapporté : les examiner
pour d'anciens sons/effets redondants. Les pistes déjà créées par ce parcours ou le
Director Niagara sont refusées pour éviter leur empilement. Aucun niveau n'est
sauvegardé et aucun composant ou AnimBlueprint n'est installé automatiquement.

Le reçu distingue plan, création à revoir et échec. Chaque sauvegarde recontrôle
le plan, les sources et les sidecars. Les deux assets ne forment pas une transaction
atomique : si la deuxième sauvegarde échoue, le premier reste listé comme sauvegardé.
Conserver et examiner ces candidats ; aucune suppression, reprise ou réutilisation
automatique d'un dossier interrompu. Les dépendances transitives restent hors de
l'empreinte des seuls assets explicitement déclarés.

## 4. Brancher une copie du personnage

1. Sur une **copie de revue** du Character existant, ajouter exactement un
   `CryptoNyanSurfaceFeedbackComponent`. Affecter le profil créé et régler
   `VariationSeed` avant BeginPlay. Son `TargetMesh` doit être le mesh principal
   exact du Character ; les meshes de vêtements ne déclenchent pas de contacts.
2. Dans une copie de l'AnimBlueprint, remplacer le clip ciblé par `AN_SurfaceFeedback`
   aux endroits voulus. Le graphe, les transitions et le rig demandent une revue
   locale ; l'outil ne les modifie pas. On peut aussi appeler `Contact` depuis
   les notifies existants, avec le vrai mesh et un socket déclaré, après revue.
3. Relier l'événement existant **OnJumped** du Character à **NotifyJump** sur le
   composant. Ce lien est explicite : une simple chute depuis un bord ne doit pas
   devenir un saut. Un saut sans sol détectable, notamment un double saut aérien,
   reste silencieux dans cette première version.
4. L'atterrissage se branche automatiquement sur `LandedDelegate` ; sa vitesse
   verticale descendante est lue avant sa remise à zéro par le mouvement.
5. Affecter les bons PhysicalMaterials à la collision des sols. La recherche suit
   un rayon vertical sur `ECC_Visibility`, en collision **simple**, avec retour du
   matériau physique. Le matériau visuel d'une texture n'est pas une classification
   de surface. Vérifier séparément landscape, meshes complexes et sols mobiles.

Le composant vise un Character solo, orienté avec Z vers le haut. Pas d'IK,
retargeting, réseau, ragdoll, simulation des fluides ou marcher sur les murs ici.
Un contact exige un mouvement au sol, la vitesse minimale et un vrai hit non
pénétrant avec normale tournée vers le haut. Aucun son n'est inventé en l'air.
La cue exacte du PhysicalMaterial passe avant le fallback ; sans correspondance,
l'événement est ignoré. Les effets restent au contact et ne suivent pas la patte.

## Cadence, durée et diagnostic

Les délais sont propres à chaque patte et aux événements saut/atterrissage. Les
contacts juste après un atterrissage sont supprimés pendant le délai de contact.
Un limiteur par composant autorise une réserve de 8 événements, puis 24/s, en plus
des budgets actifs. Il réduit les doublons des **propres callbacks du composant**,
sans certifier les notifies d'autres systèmes ni la cadence d'une démarche.
Deux composants sur le même Character sont refusés. Le notify partagé ne conserve
aucun état entre acteurs. Chaque composant a son propre tirage ; un son choisi
ne répète pas immédiatement le précédent de la même cue s'il existe des variantes.

Les sons/effets créés sont arrêtés/détruits au plus tard après `hard_stop_seconds`
de temps de jeu ou à la destruction du composant. Une saturation peut omettre un
son ou un effet ; l'émission n'est pas atomique. `EmittedEvents`, `RejectedEvents`
et `OnFeedbackEmitted` aident à vérifier cela en Blueprint. Un compteur d'émission
prouve une création de composant, pas qu'un son a été audible ou un effet visible.
Le prévisualiseur d'animation éditeur n'émet pas ; les essais se font en PIE solo.

## Tests et validation locale

```powershell
py -3.13 -m unittest discover -s loopcut/tests -p test_cryptonyan_surface_feedback.py -v
```

La suite Python vérifie plans, gardes, protocole éditeur, CLI, MCP/Studio et transfert
inerte. Elle compile aussi les règles de cadence/variantes en C++17 si un compilateur
est disponible ; cela ne compile pas les classes Unreal. Dans l'éditeur compilé,
exécuter les tests `CryptoNyan.Feedback` depuis Session Frontend → Automation.
Ils vérifient les profils et l'absence d'émission sans personnage/monde de jeu,
pas le rendu ou les collisions. La [checklist PC](local-pc-checklist.md) décrit les
essais de gameplay, les vrais fichiers audio et le build empaqueté.

Références Epic consultées : [SpawnSoundAtLocation](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/Engine/UGameplayStatics/SpawnSoundAtLocation),
[DataAssetFactory](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/DataAssetFactory),
[Landed](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/Engine/ACharacter/Landed),
[USoundWave](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/Engine/USoundWave),
[UAnimNotify](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/Engine/UAnimNotify).
Ces signatures documentées ne remplacent pas la compilation et l'essai UE 5.8 local.
