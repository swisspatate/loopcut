# Mouvements caméra — v0.26

Préparer un travelling, un mouvement de grue ou une orbite depuis des paramètres
réutilisables. Le compilateur calcule une visée vers une cible, crée les clés puis
produit une recette compatible avec le [Creative Director](creative-director.md)
existant pour Unreal 5.8. Un worker Blender séparé permet d'inspecter la trajectoire
et les coupes dans une scène ne contenant que les caméras.

## Utilisation

Recette prête à modifier : [examples/camera-moves.json](examples/camera-moves.json).
Les coordonnées sont en **mètres dans le repère Unreal** : X avant, Y droite, Z haut.
Elles doivent être adaptées au niveau et à la cible réels.

```powershell
$env:PYTHONPATH = "$PWD\scripts\addons_core"
python -m cryptonyan_asset_studio.camera_moves prepare docs\cryptonyan\examples\camera-moves.json --output D:\CryptoNyanWork\temple-camera
python -m cryptonyan_asset_studio.camera_moves check D:\CryptoNyanWork\temple-camera
python -m cryptonyan_asset_studio.camera_moves preview D:\CryptoNyanWork\temple-camera --output D:\CryptoNyanWork\temple-camera-preview --blender D:\Dev\loopcut\blender.exe
python -m cryptonyan_asset_studio.creative_director D:\CryptoNyanWork\temple-camera\cinematic.json --project D:\Jeux\CryptoNyanRunUnreal --output D:\CryptoNyanWork\temple-camera-plan.json
```

Remplacer `--blender` par le véritable exécutable. Dans Blender, le panneau
**CryptoNyan → Mouvements caméra** prépare le programme et lance l'aperçu avec
l'exécutable courant ou celui renseigné. Ce calcul est synchrone. Ouvrir ensuite
`camera-preview.blend` dans une autre fenêtre pour examiner la timeline.

Pour Unreal, utiliser le plan généré avec le parcours **dry-run puis apply** du guide
Creative Director dans la session Python de l'éditeur. L'adaptateur existant crée une
nouvelle Level Sequence et des caméras spawnables dans le dossier de revue indiqué.
Vérifier ce dossier, les cadrages et les propriétés optiques avant toute utilisation
par le jeu. Cette étape nécessite Unreal local ; elle n'est pas exécutée dans le cloud.

## Paramètres

- `move: "line"` : `start_m`, `end_m`, `target_m`. Même contrat pour un dolly avant,
  un travelling latéral, un mouvement diagonal ou une grue verticale. La cible reste fixe.
- `move: "orbit"` : `center_m`, `radius_m`, `azimuth_deg: [début, fin]` et
  `height_m: [début, fin]`. L'orbite tourne dans le plan XY autour du centre visé.
  Les hauteurs sont relatives au Z du centre. Une rampe de hauteur donne une hélice.
- `frames` : durée du plan ; `samples` : nombre de clés, entre 2 et 128 et au plus
  le nombre de frames. Les première et dernière images sont incluses. Les clés
  intermédiaires sont arrondies sur des frames entières et interpolées linéairement.
- `easing: "linear"` ou `"smoothstep"` : progression uniforme ou adoucie aux extrémités,
  approximée par les échantillons. Augmenter `samples` pour un mouvement plus fidèle.
- Jusqu'à 16 plans, 120 fps et 10 minutes au total, suivant les limites Director.
  Les cibles trop proches d'une singularité verticale sont refusées. Les orbites
  dépassant deux tours ou insuffisamment échantillonnées sont également refusées.

## Conversion et validation

La préparation fige `camera-program.json` et `cinematic.json`. Leur cohérence est
recalculée avant un aperçu. Dans Blender, X = X Unreal, Y = −Y Unreal et Z = Z Unreal.
Le worker oriente l'axe local −Z de la caméra vers la cible et conserve +Y comme axe
vertical de caméra. Il utilise le helper Loopcut pour les actions classiques ou à
slots, contrôle réellement la direction à chaque clé puis produit un `.blend`, un
rapport et un reçu avec hashes. La scène ouverte lors du lancement reste disponible.

L'aperçu contient seulement les caméras, leurs clés et les marqueurs de coupe.
Il n'importe pas tes niveaux, ne calcule pas les occlusions et n'évite pas les murs.
La visée est vérifiée aux clés ; entre elles, la trajectoire est une approximation
linéaire. Le roll, les cibles animées, la détection de collision et les splines restent
à développer.

L'aperçu Blender utilise 50 mm, tandis que l'adaptateur Unreal conserve les valeurs
par défaut de CineCameraActor. Focale, capteur, profondeur de champ et exposition
nécessitent une revue dans les deux logiciels : des cadrages identiques ne sont pas
promis. Les tests Unreal utilisent des doubles stricts d'API ; seule une exécution
locale peut qualifier Unreal 5.8.

Voir la [checklist locale](local-pc-checklist.md) pour les points restants.
