# Essayage animé sur le personnage existant — v0.29

Ce module contrôle des vêtements **déjà liés au rig existant**, sur plusieurs
actions explicitement choisies. Il réutilise le sampler d'Animation Doctor,
l'audit des poids de Rig Doctor et les utilitaires géométriques du worker de
vêtements. Il ne génère ni vêtements ni os et ne change aucun poids. Pour un
vêtement encore statique, commencer par [l'ajustement et transfert](garment-workflow.md)
et utiliser la copie obtenue avec son nom `CN_GarmentCandidate` dans la spécification.

## Préparer une copie autonome

Dans Blender, enregistrer un `.blend` de travail avec les textures intégrées et
sans bibliothèques liées. Prévoir un corps fermé, à normales cohérentes vers
l'extérieur, ou un proxy de collision fermé lié au même rig. Les vêtements peuvent
être ouverts ; leur seule contrainte de déformation est un modificateur Armature
actif, à groupes de sommets, ciblant le même rig que le corps. Le parentage normal
au rig est accepté. Les shape keys présentes sont évaluées et conservées.

Utiliser les noms réels du corps, des vêtements, de l'armature, des actions et des
os dans [l'exemple JSON](examples/animated-wardrobe.json). Enregistrer les actions
avec un utilisateur ou « Fake User » pour qu'elles existent après réouverture.
Les actions à plusieurs slots exigent `action_slot`, identifiant exact déjà pris
en charge par Animation Doctor. Une fenêtre doit inclure ses deux extrémités ;
chaque capture conserve ses propres déclarations de mouvement/contact.

```powershell
$env:PYTHONPATH = 'D:\Dev\loopcut\scripts\addons_core'
python -m cryptonyan_asset_studio.wardrobe_review `
  'D:\CryptoNyanWork\character-packed.blend' `
  'D:\CryptoNyanWork\wardrobe.json' `
  --output 'D:\CryptoNyanWork\try-on-001' `
  --blender 'C:\Program Files\Blender Foundation\Blender 4.3\blender.exe'
```

Le dossier de destination doit être nouveau. Le panneau **CryptoNyan → Essayage
des vêtements animés** utilise exactement ce parcours, avec un Blender enfant
isolé. Le calcul est synchrone et peut bloquer le panneau jusqu'à son terme.
La scène ouverte reste inchangée ; enregistrer une copie avant de lancer l'essai.

## Examiner le résultat

- `result.json` : statut, hash de la source et de chaque copie ; un échec ne valide rien.
- `wardrobe.json` : audit des poids du corps/vêtements, audit des poses par action,
  mesures par vêtement/frame, indices et traversées d'arêtes bornés à 100 preuves.
- `review.html` : table autonome, liens vers les copies et tous les échantillons CSV.
- `review-01.blend`, etc. : une copie par fenêtre, avec l'action choisie, NLA
  désactivé, pire frame ouverte, vêtement correspondant sélectionné et marqueurs
  `CN_WR_` aux frames signalées. Les marqueurs préexistants restent conservés.
- `source.blend` et `request.json` : snapshot vérifié et requête normalisée.

La pire frame est choisie par profondeur négative maximale estimée, puis nombre
de sommets suspects, puis arêtes traversantes ; les égalités conservent la première
frame. Chaque vêtement est analysé séparément contre le corps. La CLI retourne 1
si des poses/vêtements ou des poids sont signalés, 0 sinon, 2 en cas d'échec.
Même 0 ne constitue pas une validation artistique ou une autorisation d'adoption.
Les avertissements d'Animation Doctor restent dans le rapport sans modifier ce
code de sortie centré sur les vêtements/poids.

## Portée des mesures

Le signe de distance utilise la normale du triangle le plus proche, comme le
premier worker de vêtements. Ce diagnostic peut être ambigu près d'arêtes,
sur des surfaces concaves ou auto-intersectées ; il n'est pas une classification
volumique robuste. Le corps doit rester fermé et orienté à chaque frame.

Des rayons BVH testent aussi les arêtes des deux maillages contre l'autre surface,
en excluant une marge égale à la tolérance aux extrémités. Cela repère notamment
un grand panneau de tissu qui traverse le corps alors qu'aucun de ses sommets
n'est à l'intérieur. Le compteur est celui des **arêtes ayant au moins un hit**,
pas un nombre de triangles, de contacts physiques ni de traversées multiples.
Les contacts coplanaires et ceux dans la marge ne sont pas détectés par ces rayons.

Limites : 1–8 vêtements, 1–8 fenêtres, 240 frames au total, 10 000 sommets par
vêtement/20 000 cumulés, géométrie évaluée du corps bornée par les helpers existants
(50 000 sommets/100 000 polygones), budget cumulé de 8 millions de sommets + triangles
sur les frames, entrée 512 Mio, copies de revue cumulées 1 Gio, timeout par défaut
180 s/maximal 600 s. Les copies peuvent rester partielles après échec ; seul le
reçu final `review_required` indique que le parcours a abouti.

Les modificateurs supplémentaires, caches/simulations, géométrie vide, corps ouvert,
transformations réfléchies/singulières et mapping ambigu sont refusés. Les poses
ordinaires avec contraintes/IK sur le rig sont évaluées ; les contraintes d'objet
sur les maillages sont refusées. Aucun test continu entre les frames, aucune
collision vêtement/vêtement, simulation textile ou correction automatique.
Un mesh fin traversant entre deux frames peut donc échapper au diagnostic.

## À valider sur le PC

Voir la [checklist centralisée](local-pc-checklist.md). Tester le vrai personnage,
ses shape keys, ses slots, ses unités et plusieurs courses/sauts/accroupissements.
Si le corps a des ouvertures, préparer un proxy fermé adapté. Examiner les copies
dans Blender Windows, puis les vêtements dans Unreal 5.8 sur une copie de test :
Skeleton, influences, normales, LOD et éventuels réglages Chaos Cloth.
Le rendu Windows, les vrais assets et le runtime Unreal ne sont pas exécutés dans
le cloud. Cette version ne réalise aucun import ni adoption automatique dans le jeu.
