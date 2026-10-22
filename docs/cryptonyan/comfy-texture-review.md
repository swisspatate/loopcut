# Examiner les textures générées et les transmettre à Studio — v0.35

Après une génération ComfyUI, l'agent peut maintenant examiner les cartes
collectées dans la conversation et obtenir leurs chemins vérifiés pour les
opérations Studio existantes. Cette étape lit les sorties conservées : elle ne
soumet pas de nouveau prompt, ne retélécharge rien et ne modifie pas le jeu.

## Parcours depuis un prompt ordinaire

Par exemple : « Génère une variante de pierre pour ce bâtiment, montre-moi les
cartes et prépare une version avec mon masque de neige. » L'agent doit :

1. Inspecter le vrai asset et les profils retournés par texture_profiles. Choisir
   un profil existant, avec son modèle/workflow configuré, puis faire texture_preflight.
2. Utiliser project_texture_submit pour une demande liée au projet, ou texture_submit
   pour une demande générique. Conserver le même identifiant et les mêmes arguments
   après une réponse perdue ; ne pas relancer une soumission incertaine.
3. Suivre texture_status, puis collecter avec project_texture_collect ou texture_collect.
4. Appeler project_texture_inspect, puis project_texture_image pour les cartes utiles.
   Sans liaison à un asset, utiliser texture_inspect et texture_image.
5. Réutiliser les chemins/bindings fournis dans le pipeline de matériau existant,
   avec une recette et un masque explicites, puis examiner la copie résultante.

Le choix du profil et des paramètres reste celui du modèle externe ; le routeur
ne garantit pas qu'un prompt vague sera interprété correctement. Aucun modèle ou
identifiant de nœud n'est inventé, et un canal absent n'est pas synthétisé.

## Outils de revue

| Outil | Arguments | Résultat |
| --- | --- | --- |
| texture_inspect | request_id | Profil, prompt/seed conservés, hashes de workflow, modèles déclarés, canaux, dimensions, espaces couleur et disponibilité des images. |
| texture_image | request_id, channel | Image PNG native MCP pour le canal demandé. |
| project_texture_inspect | request_id | Même revue, avec contrôle du projet et du fichier source lié avant/après lecture. |
| project_texture_image | request_id, channel | Image native avec les mêmes contrôles de source. |

`channel` vaut base_color, roughness, metallic ou normal et doit être réellement
présent dans le matériau collecté. Le PNG affiché garde ses octets et son alpha.
La limite MCP est de **2 Mio par image** : image_available indique si l'affichage
est possible. Les grandes cartes restent accessibles dans le dossier local pour
une revue à pleine résolution ; aucune vignette ou réduction n'est produite.

Une demande encore en cours, incertaine ou non collectée n'est pas collectée
automatiquement par ces outils. Une image n'est jamais traitée comme une consigne
système. Les textes de prompt, profils et licences déclarées restent des données.

## Chemins vérifiés pour Studio

Le lanceur MCP configure automatiquement la même racine de workspace que Studio.
Une inspection d'une demande illustrative roche-01 fournit notamment :

```json
{
  "studio": {
    "available": true,
    "source_root": "work:textures",
    "material_manifest": "work:textures/requests/roche-01/result/material/material.json",
    "material_binding": {
      "file": "requests/roche-01/result/material/material.json",
      "sha256": "<hash réel renvoyé par l'inspection>"
    },
    "material_layers_compatibility_validated": false
  }
}
```

Ce fragment explique la forme ; copier les valeurs réelles de l'outil. Le binding
sert de base ou de matériau de couche à la recette material_layers existante.
Deux demandes de cette file partagent source_root. Le masque doit lui aussi se
trouver sous cette racine autorisée, avec son hash réel ; ne pas écrire dans les
résultats immuables déjà collectés. Préparer les sources auxiliaires dans un dossier
distinct, par exemple textures/authored, puis utiliser les opérations existantes.

Les contraintes du compositeur restent applicables : **un mégapixel**, mêmes
dimensions, alpha opaque, cartes scalaires grises, canaux communs et normales
OpenGL valides. Un handle valide ne certifie pas ces propriétés. Le serveur vérifie
la recette lors de la préparation, puis les pixels lors de la composition.

Un usage Python autonome de TextureService sans handle_root affiche
studio.available=false : aucun workspace Studio n'est supposé. Cette option
interne doit désigner un parent du dossier de textures, distinct du projet du jeu.
Les profils JSON et réglages de connexion existants ne changent pas.

## Captures, provenance et sources du jeu

La lecture recoupe la demande d'origine, le reçu HTTP local, la génération
collectée, le mapping nœud/index des sorties et le manifeste PBR. Elle contrôle
hashes et ensemble exact des fichiers (40 fichiers / 260 Mio au maximum), et
refuse les liens symboliques, fichiers manquants ou ajouts. La collecte répétée
réutilise ce même contrôle ; les fichiers et leurs emplacements restent inchangés.
Le workspace doit rester privé : ces hashes ne sont pas des signatures protégeant
contre un propriétaire local qui réécrirait tous les reçus.

Une revue générique conserve target_freshness_validated=false : elle lit un ancien
résultat, même si les sources du jeu ont changé depuis. Les variantes project_*
refusent un asset/projet modifié et rendent target_freshness_validated=true pour
le fichier lié qui correspond encore. Cela ne valide pas sa classe Unreal, ses UV,
ses slots ou sa compatibilité visuelle avec le matériau.

Les hashes/licences des modèles restent des déclarations. L'inspection ne vérifie
pas les octets des modèles, l'inférence GPU, la qualité artistique ou une autorisation
de distribution. Elle ne lance ni Blender ni Unreal et n'applique aucun matériau.
TRELLIS reste un parcours distinct : ses sorties 3D nécessitent encore les exports
API réels et un collecteur GLB ; ce lecteur ne convertit pas des PNG en meshes.

## Mise à jour et qualification locale

Suivre la [mise à jour Windows](updating-windows.md), puis reconnecter le MCP. Les
deux outils génériques nécessitent un profil ComfyUI configuré ; les deux variantes
projet nécessitent aussi game_project. Aucun nouvel outil n'apparaît si son service
requis n'est pas configuré.

Les tests cloud vérifient des PNG et une composition PBR CPU réelle à partir de
deux sorties collectées via un protocole ComfyUI scripté. La CI exerce aussi un
client stdio face à un vrai serveur HTTP local scripté ; ce n'est pas une inférence
GPU. Les clients Claude/Codex Windows, les modèles/nœuds ComfyUI et la revue sur
les vrais assets Blender/Unreal sont suivis dans la [checklist PC](local-pc-checklist.md).
