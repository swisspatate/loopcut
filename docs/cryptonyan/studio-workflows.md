# Enchaîner les opérations Studio — v0.33

Un parcours relie **1 à 8 opérations existantes**, dans un ordre explicite. Il utilise
la file Studio, ses identifiants stables, son annulation et ses contrôles de sources.
Il ne crée pas un second service d'agents et ne déduit pas les recettes depuis une phrase.

## Depuis l'agent

1. Lire `studio_guide` avec `{"capability": "workflow_automation"}`.
2. Appeler `studio_workflow_template` avec un modèle et les vrais paramètres requis.
   Cela prépare un objet `workflow`, sans exécution ni validation détaillée des recettes métier.
3. Soumettre cet objet avec `studio_submit`, `operation: "workflow_run"`,
   `arguments: {"workflow": ...}` et un identifiant stable.
4. Suivre `studio_operation` avec des lectures espacées. Le reçu montre l'étape en
   cours, les états par étape et le nombre terminé. `studio_cancel` vise le parcours entier.
5. Lire les rapports et images par `studio_artifact` une fois le parent `succeeded`.
   `studio_jobs` retrouve l'identifiant après reconnexion.

Une erreur, une annulation, un dépassement de budget ou un critère rejeté bloque
**toutes les étapes suivantes**. Les étapes déjà terminées et les sorties partielles
restent sur disque ; elles ne sont jamais rejouées automatiquement.

## Modèles disponibles

| Modèle | Entrées explicites | Étapes |
| --- | --- | --- |
| `camera_preview` | `recipe` | Préparer le programme, puis créer l'aperçu Blender. |
| `material_layers` | `recipe`, `source_root` | Figer les cartes/masques PBR, puis composer les variantes. |
| `modular_preview` | `recipe`, `catalog`, `source_root` | Préparer le niveau modulaire, puis importer les GLB dans l'aperçu Blender. |
| `image_preview` | `reference`, `recipe`, `source_root` | Préparer Image Workshop, puis construire sa scène Blender. |
| `rig_repair_copy` | `source`, `specification`, `policy` | Auditer le rig, préparer le plan explicite, puis créer/vérifier une copie réparée. |

Seul `material_layers` ne demande pas Blender. Les noms d'objets/os/actions, les
recettes, les matériaux et la politique de réparation viennent d'une inspection
réelle. Le modèle ne choisit pas une politique, un workflow ComfyUI ou un modèle GPU.
Une réparation crée un candidat à examiner ; elle ne remplace pas le personnage.

Exemple : `studio_workflow_template` reçoit `template: "camera_preview"` et
`inputs: {"recipe": <recette caméra inspectée>}`. Une recette complète et exécutable
sur une scène de démonstration est fournie dans
[workflow-camera-preview.json](examples/workflow-camera-preview.json).

## Schéma d'un parcours

```json
{
  "schema": "cryptonyan.studio-workflow/1",
  "id": "camera-review",
  "steps": [
    {"id": "prepare", "operation": "camera_prepare", "arguments": {"recipe": {}}},
    {"id": "preview", "operation": "camera_preview", "arguments": {
      "bundle": {"from_step": "prepare", "file": ""}
    }}
  ]
}
```

Le `{}` de recette illustre la structure ; il faut une vraie recette caméra, telle
que celle du fichier d'exemple. Les identifiants de parcours et d'étapes commencent
par une lettre minuscule, puis contiennent des lettres minuscules, chiffres, `_`
ou `-`, au maximum 32 caractères. Chaque étape a un identifiant unique ; les noms réservés de Windows sont refusés.

Une liaison `from_step` ne désigne qu'une **étape précédente de ce parcours** :

- `file: ""` : dossier de sortie de cette étape ;
- `file: "plan.json"` : fichier relatif sous ce dossier ;
- les chemins absolus, `..`, antislashs et liens symboliques sont refusés.

Les liaisons sont autorisées uniquement pour les arguments de type chemin ou liste
de chemins. Les objets de recette restent des données littérales ; aucun texte,
champ de résultat, expression ou commande n'est interpolé. Les parcours imbriqués,
les boucles, les cycles et les étapes futures sont refusés.

Les 18 opérations primitives restent disponibles. Un parcours manuel peut, par
exemple, relier `comparison_plan` à `unreal_handoff`. Cela **produit un script inerte** :
aucune session Unreal n'est lancée et aucun asset du jeu n'est adopté.

## Critères de résultat

Une opération d'audit peut terminer normalement tout en signalant des défauts.
Le statut technique `succeeded` ne signifie donc pas que son résultat est sans défaut.
Ajouter des critères explicites lorsque la suite doit être bloquée :

```json
"checks": [
  {"path": ["flagged_samples"], "equals": 0}
]
```

Cet exemple s'applique au résultat de `wardrobe_review`, après vérification du
schéma réel. Au maximum huit critères par étape, chacun visant un champ imbriqué
ou un indice de tableau ; la valeur attendue est un scalaire JSON. Une comparaison
est exacte et sensible au type : `true`, `1` et `1.0` sont distincts. Un champ absent
ou différent rejette l'étape et bloque la suite. Le reçu indique les chemins des
critères et leur résultat ; le rapport complet reste dans le journal de l'étape.

Un contrôle de champ ne certifie pas la qualité visuelle, la jouabilité, la collision
continue ou la bonne décision d'un modèle. Sans critère, seul l'achèvement technique
conditionne la suite. Le parcours ne déduit jamais un seuil de qualité.

## Fichiers et reprise

Tout reste sous `<workspace-client>/studio/operations/<request_id>/` :

- `request.json` et `operation.json` : requête et reçu parent ;
- `output/workflow.json` : recette figée du parcours ;
- `output/workflow-status.json` : états et résultats des critères ;
- `output/steps/<id>/request.json`, `result.json`, `step.json` : arguments résolus,
  résultat et manifeste de l'étape ;
- `output/steps/<id>/output/` : sorties du module existant.

Avant une liaison, les tailles, hashes, ensemble de fichiers et reçu de l'étape
productrice sont vérifiés. Une dernière vérification contrôle toutes les étapes
terminées avant l'indexation du parent. Cette vérification peut encore faire échouer
le parcours après le calcul des étapes ; le statut parent détermine la disponibilité
du résultat complet. Un fichier modifié, ajouté ou remplacé
bloque la suite. Les contrôles ne remplacent pas un système de fichiers privé :
le workspace doit rester réservé à ce service et les sources ne doivent pas être
modifiées pendant leur utilisation.

Le service vérifie tous les runtimes et chemins littéraux avant d'accepter le
parcours, puis les recontrôle au démarrage des étapes. Il ne copie pas toutes les
sources au moment de la soumission : chaque module garde ses propres captures et
contrôles. Les liens vers des étapes précédentes utilisent leurs sorties figées.

Après une réponse perdue, réutiliser le même identifiant et exactement les mêmes
arguments. Après un redémarrage, un parcours inachevé devient `interrupted`, ses
étapes actives sont marquées incertaines et ses étapes en attente sont bloquées.
Aucune reprise partielle ni relance n'a lieu. Examiner les sorties et les anciens
processus Blender avant une nouvelle tentative volontaire sous un nouvel identifiant.

## Limites et essais locaux

Un parcours occupe **une place et un worker** de la file existante. Les étapes sont
séquentielles et ne cèdent pas le worker à un autre job. Le budget de 600 secondes
est partagé par le parcours ; les délais et contrôles des modules s'appliquent aussi.
L'annulation CPU reste coopérative aux frontières d'étapes ; Blender utilise l'arrêt
existant des processus enfants. Les limites de 2 048 fichiers et 2 Gio concernent
le résultat parent, avec un contrôle cumulé entre étapes. Voir les détails de la
[file en arrière-plan](background-operations.md).

Cette version ne relie pas les opérations Studio aux appels réseau ComfyUI. Utiliser
les outils de profils, preflight et collections existants pour la génération ; les
cartes déjà collectées peuvent alimenter le modèle `material_layers`. Il n'y a pas
d'arbitrage GPU global, de reprise après crash ou d'exécution Unreal automatique.

Les tests cloud couvrent les vraies chaînes PBR, caméra Blender, GLB modulaires, copie de réparation de rig et recette Image Workshop rendue/exportée,
ainsi qu'un client stdio réel. Windows Blender, les
vrais clients Claude/Codex, Unreal 5.8 et ComfyUI GPU restent à qualifier sur le PC :
[checklist centralisée](local-pc-checklist.md).

## CLI hors MCP

```powershell
$env:PYTHONPATH = 'D:\Dev\loopcut\scripts\addons_core'
python -m cryptonyan_asset_studio.studio_workflows templates
python -m cryptonyan_asset_studio.studio_workflows make camera_preview inputs.json
python -m cryptonyan_asset_studio.studio_workflows validate workflow.json
```

Ces commandes affichent du JSON et ne lancent aucune opération. `validate` vérifie
la structure du parcours ; les recettes détaillées et les runtimes sont contrôlés
par la soumission et les modules existants.
