# Animation Doctor pour les animations existantes — v0.16

Ce module audite un rig et une action **déjà présents dans un fichier Blender**.
Les noms des os sont configurables : aucun besoin de remplacer ton personnage
par le chat de démonstration. Il produit des mesures, des avertissements et des
repères de contacts pour préparer les effets. Il ne corrige ni ne sauvegarde le rig.

## Utilisation sur ton PC

Depuis le checkout Loopcut, dans PowerShell :

```powershell
$env:PYTHONPATH = "$PWD\scripts\addons_core"
Copy-Item docs\cryptonyan\examples\animation-capture.json D:\AnimationReview\run-config.json
```

Modifier `run-config.json` avec le nom réel de l'armature, de l'action et de l'os
racine, puis les os à examiner (pattes, bassin, tête, queue…). L'exemple utilise
des noms fictifs. Choisir les bornes réelles du clip ; pour une boucle, inclure
la pose finale qui doit rejoindre la première. Le dernier frame doit être atteint
exactement par `step_frames`. Le temps zéro du rapport correspond à `start_frame`.

```powershell
python -m cryptonyan_asset_studio.animation_doctor capture `
  D:\AssetsReview\character.blend D:\AnimationReview\run-config.json `
  --blender "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe" `
  --output D:\AnimationReview\run-001
```

Adapter le chemin Blender à l'installation. Python 3.11+ est nécessaire pour le
lanceur. Le dossier de sortie doit être **nouveau**. Pour un agent Claude Code ou
Codex, la même commande est l'interface disponible ; cette version n'ajoute pas
de commande MCP ni de nouveau type à la file de missions. Aucun appel de modèle.

Fichiers produits :

- `source.blend` : instantané de la source ; son hash et celui de l'original sont contrôlés.
- `request.json` : paramètres explicites de l'audit.
- `trace.json` : poses évaluées, temps, métadonnées du rig et provenance.
- `audit.json` : mesures, seuils, limites et avertissements.
- `events.json` : candidats de contacts liés à l'identité de l'audit.

Codes de sortie : **0** aucun avertissement dans le périmètre mesuré ; **1** rapport
disponible avec avertissements ; **2** échec de configuration/exécution. Un code 0
ne valide pas les contrôles exclus ou non évalués. Un échec peut laisser un dossier
partiel : ne pas le réutiliser comme un audit terminé. `audit.json` n'est écrit
qu'après capture complète, validation des données et contrôle des hashes.

## Mesures et sens des résultats

| Contrôle | Mesure | Limite |
|---|---|---|
| Boucle | Distance/orientation entre première et dernière pose, dans le repère rigide de la racine | Pas de continuité des vitesses à la jonction |
| Racine | Déplacement net, distance parcourue, excursion et rotation maximale | Avertissement de dérive uniquement si `motion: in_place` |
| Mouvement brusque | Vitesse, accélération par différences finies, vitesse angulaire | Racine en monde ; autres os dans le repère racine ; pas de jugement artistique |
| Glissement | Vitesse 3D maximale de l'origine de l'os pendant un appui déclaré | Exige la trajectoire mondiale et les bornes d'appui échantillonnées |
| Rig | Os sélectionnés, parents, drapeau de déformation et types de contraintes | Pas d'audit des poids, de retargeting ni d'autoréparation |

Les unités sont **mètres, secondes, degrés**. Blender est converti avec
`scene.unit_settings.scale_length` et `fps / fps_base`. Les rotations de trace sont
des quaternions **WXYZ** unitaires ; `q` et `-q` représentent la même orientation.
Les seuils par défaut sont des points de départ, à adapter au personnage et à ses
pouvoirs. Un dash intentionnel peut dépasser un seuil sans être un défaut.

`motion` déclare l'intention du clip ; il n'ajoute pas de déplacement. `contact_space`
déclare si les poses contiennent réellement le mouvement mondial du personnage.
Un clip sur place joué par un personnage mobile doit garder `unknown` tant qu'une
trajectoire réelle n'a pas été intégrée aux poses. Ne pas passer à `world` seulement
pour obtenir un résultat positif. Un clip sur place testé à l'arrêt peut utiliser
`world` si c'est bien la situation évaluée.

Exemple d'appui, à ajouter dans `settings.contacts` après observation :

```json
[{"bone": "FootCustom", "start_s": 0.1, "end_s": 0.3}]
```

Les contacts ne sont pas devinés. Les deux bornes doivent correspondre à des temps
échantillonnés ; sinon le contrôle indique `not_assessed_insufficient_samples`.
La mesure porte sur l'origine de l'os, pas sur la semelle, le terrain ou une plateforme
mobile. Pour ce dernier cas il faudra un futur repère de contact relatif au support.

## Repères pour les effets spéciaux

Chaque début d'appui déclaré produit un candidat `contact_start`, avec os, temps,
statut de glissement et `approved: false`. Un outil Unreal pourra ensuite associer
ce repère à poussière, éclaboussure, étincelle ou son selon la surface. Cette version
**ne crée pas d'AnimNotify ni de système Niagara**. Il faut vérifier le point de
contact, le sens des axes, le socket, le looping et la vitesse effective avant application.
Les événements de dash/atterrissage et la politique anti-doublons runtime restent à ajouter.

## Capture Blender et limites d'exécution

Le worker réutilise le lanceur isolé de Loopcut : `--factory-startup`, auto-exécution
des scripts désactivée, configuration temporaire, temps limité (120 s, maximum 600 s),
arrêt du processus en cas de timeout. Il ouvre uniquement l'instantané et ne l'enregistre
jamais. Les contraintes/IK passent par le dependency graph. L'action choisie remplace
l'action active ; le NLA de cette armature est désactivé et les bases de pose sont
réinitialisées dans le processus. Les animations des autres objets et leurs contraintes
restent celles de la scène. Il ne s'agit donc pas d'une mesure du mélange NLA final.

Utiliser un fichier de travail autonome et de confiance : les bibliothèques liées,
simulations et caches externes pris en charge par les garde-fous sont refusés. Les
drivers nécessitant un script Python, extensions tierces, simulations non prises en
charge ou dépendances externes doivent être cuits puis vérifiés localement. Désactiver
les scripts n'est pas une sandbox de sécurité pour des fichiers malveillants.
Les transformations réfléchies/singulières sont refusées. Les échelles animées,
cisaillements et déformations ne sont pas audités.

Budgets : source ≤512 MiB ; 512 os dans le rig, 64 os sélectionnés plus la racine ;
2–2001 échantillons, clip ≤600 s, ≤128 fenêtres d'appui, JSON ≤32 MiB.
Une action sans canaux de pose, une mauvaise plage ou un os absent fait échouer la
capture. Blender 4.4+ : si plusieurs slots OBJECT existent, ajouter `action_slot`
avec l'**identifier** exact. Le lecteur de canaux réutilise celui de Loopcut.
Le parcours est testé avec Blender Linux 4.3.2 ; les slots et Blender Windows restent
à vérifier sur les versions installées.

## Interface de trace et Unreal

Le cœur Python accepte aussi une trace normalisée, pour permettre un futur sampler Unreal :

```json
{
  "schema": "cryptonyan.animation-trace/1",
  "clip": "Run",
  "samples": [
    {"time_s": 0, "poses": {
      "Origin": {"position": [0,0,0], "rotation": [1,0,0,0]},
      "FootCustom": {"position": [0.1,0,0], "rotation": [1,0,0,0]}
    }},
    {"time_s": 1, "poses": {
      "Origin": {"position": [0,0,0], "rotation": [1,0,0,0]},
      "FootCustom": {"position": [0.1,0,0], "rotation": [1,0,0,0]}
    }}
  ]
}
```

Sauvegarder l'objet `settings` seul dans un second JSON puis :

```powershell
python -m cryptonyan_asset_studio.animation_doctor audit trace.json settings.json --output audit-001
```

Les poses doivent toutes être mondiales, dans un repère orthonormé commun et avec
la même convention de quaternion. Ne pas mélanger les transforms locaux des os
d'Unreal avec ces poses. Un exporteur devra composer la hiérarchie, traiter le root
motion, convertir cm→m et la convention d'axes, puis tester contre l'éditeur.
**La lecture directe des `.uasset`/AnimSequence n'est pas implémentée.** Si ton rig
n'existe que dans Unreal, il faudra préparer un export de travail Blender, ou
développer ce sampler éditeur. Aucun asset privé du jeu n'a servi aux fixtures publiques.

Tests : `python -m unittest discover -s loopcut/tests -p test_cryptonyan_animation.py -v`.
Définir `LOOPCUT_BLENDER` pour activer les tests réels si Blender n'est pas dans PATH.
Voir la [checklist PC](local-pc-checklist.md) pour la validation du personnage réel.
