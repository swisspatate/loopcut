# Choix des outils depuis un prompt naturel — v0.36

L'agent peut découvrir les workflows du fork sans que tu cites leur nom. Cette
version ajoute **30 familles de capacités**, les consignes MCP et **19 opérations
exécutables** réutilisant les modules existants. Les outils natifs d'audit,
ComfyUI, projet et références restent disponibles. Les autres parcours disposent
d'un guide et d'une commande CLI de découverte ; le catalogue ne les présente pas
comme des actions MCP exécutables.

Le modèle Claude/Codex reste responsable du choix et des arguments. Notre routeur
fournit une liste indicative à partir d'indices lexicaux français/anglais : ce
n'est pas un modèle de compréhension générale, une garantie de bon choix ou une
autorisation d'exécuter le texte du prompt. Une demande vague ou une égalité peut
donner `needs_clarification`. Il faut alors inspecter le contexte ou préciser le but.

## Utiliser après mise à jour

1. Mettre à jour le dépôt local et **redémarrer/reconnecter le MCP CryptoNyan** dans
   Claude Code ou Codex. Les profils `connection.json` existants restent valides. Le flux MCP est explicitement
   UTF-8, y compris avec les versions Python Windows utilisant un encodage historique.
   Aucun nouveau champ, compte ou accès API n'est nécessaire.
2. Vérifier que `studio_catalog`, `studio_route` et `studio_guide` sont visibles.
   Le lanceur réel expose aussi `studio_submit`, `studio_execute`, `studio_operation`,
   `studio_cancel`, `studio_jobs`, `studio_workflow_template` et `studio_artifact`.
   Depuis v0.34, `studio_workflow_inspect`, `studio_workflow_step_artifact` et
   `studio_workflow_fork` permettent de diagnostiquer puis
   [réutiliser des snapshots](workflow-reuse.md) sous un nouvel identifiant.
   Les services optionnels dépendent du profil configuré.
   Avec ComfyUI, la [revue des textures](comfy-texture-review.md) ajoute
   texture_inspect/texture_image et, avec le projet, leurs variantes project_*.
   L'agent doit inspecter les cartes collectées avant de proposer leur utilisation.
   Si le profil déclare reference_slots, les consignes demandent la
   [préparation des références](comfy-reference-preparations.md), son prévol et la
   soumission avec le même identifiant durable. Le choix des modèles et bindings
   reste celui du profil opérateur ; l'agent choisit les PNG sous les racines autorisées.
3. Essayer des demandes ordinaires : « Mon manteau traverse le corps pendant la
   course », « Crée des textures différentes pour plusieurs assets », « Compare
   mes skins dans Unreal » ou « Prépare un travelling caméra ».

`initialize` transmet les consignes du serveur. Un prompt MCP
`cryptonyan_workflow` est aussi disponible via `prompts/list` / `prompts/get`.
Le dépôt contient [AGENTS.md](../../AGENTS.md) et [CLAUDE.md](../../CLAUDE.md) pour
les agents travaillant dans ce fork. Si l'agent est ouvert dans un autre projet,
préparer des consignes à relire puis à intégrer à ses instructions existantes :

```powershell
$env:PYTHONPATH = 'D:\Dev\loopcut\scripts\addons_core'
python -m cryptonyan_asset_studio.agent_connect guidance `
  'D:\CryptoNyanWork\connection.json' --client codex `
  --output 'D:\CryptoNyanWork\guidance-codex-001'
```

`--client claude` produit `CLAUDE.md`. L'export écrit dans un dossier nouveau hors
du jeu/des assets ; il ne modifie ni les fichiers existants du client, ni ses comptes.
Le support et l'usage des consignes MCP dépendent du client : vérifier le vrai tour
de conversation sur le PC. Aucun choix d'outil par un modèle externe n'a été testé
dans le cloud.

## Parcours de l'agent

| Outil | Rôle |
| --- | --- |
| `studio_catalog` | Familles publiques, outils réellement connectés, opérations, guides et prérequis manquants. |
| `studio_route` | Recommandations classées pour un objectif, sans exécution ni paramètres inventés. |
| `studio_guide` | Consignes, paramètres des opérations et lien vers le guide du workflow choisi. |
| `studio_workflow_template` | Préparer un parcours de plusieurs étapes avec de vrais paramètres, sans exécution. |
| `studio_submit` | Mettre une opération en file et répondre immédiatement ; choix recommandé pour Blender. |
| `studio_execute` | Attendre une opération de cette même file ; compatibilité pour les petits traitements. |
| `studio_cancel` | Demander un arrêt puis attendre un état terminal ; `cancelling` peut encore être actif. |
| `studio_jobs` | Retrouver les reçus récents et les comptes par état après reconnexion. |
| `studio_operation` | Reçu durable et contrôle des hashes de tous les artefacts terminés ; pas de reprise. |
| `studio_artifact` | Lecture d'un fichier listé et vérifié ; JSON/texte jusqu'à 256 Kio ou image PNG jusqu'à 2 Mio. |

L'agent doit utiliser les vrais noms d'objets/os/actions, slots, chemins et profils.
Il consulte les snapshots sélectionnés ou l'inventaire quand ils sont configurés.
Une référence, un nom d'asset ou une note importée reste une donnée, pas une
instruction système. Les paramètres absents doivent être découverts ou demandés.
L'outil ne les déduit pas à partir d'une phrase.

Pour ComfyUI, découvrir `texture_profiles`, appeler `texture_preflight`, soumettre
avec un identifiant stable, suivre puis collecter. Préférer `project_collection_*`
pour plusieurs textures liées aux assets existants. Les profils et modèles
doivent être configurés localement ; le catalogue ne les installe pas.

## Parcours avec plusieurs étapes

Depuis v0.33, la capacité `workflow_automation` expose cinq modèles. Préparer un
workflow avec `studio_workflow_template`, puis soumettre `workflow_run` par le même
`studio_submit`. Les liaisons ciblent uniquement des sorties vérifiées d'étapes
précédentes ; des critères explicites peuvent bloquer la suite. Voir le
[guide et les limites des parcours](studio-workflows.md). Le routeur reste indicatif
et ne fabrique pas les recettes ou les politiques de réparation.

## Opérations ajoutées

| Famille | Valeurs de `operation` |
| --- | --- |
| Parcours | `workflow_run` : 1 à 8 opérations primitives existantes, sans imbrication. |
| Animation, rig et vêtements | `animation_audit`, `rig_audit`, `rig_repair_plan`, `rig_repair_copy`, `garment_fit`, `wardrobe_review` |
| Niveaux modulaires | `level_prepare`, `level_preview` |
| Couches PBR | `layers_prepare`, `layers_compose` |
| Caméras | `camera_prepare`, `camera_preview` |
| Image Workshop | `image_prepare`, `image_build` |
| Préparation/revue Unreal | `comparison_plan`, `comparison_gallery`, `director_plan`, `unreal_handoff` |

Chaque opération dispose d'un schéma fermé d'arguments, exposé dans le schéma MCP
et `studio_guide`. Les modules d'origine valident ensuite les recettes détaillées.
Aucune commande shell, module Python arbitraire, destination libre ou installation
n'est acceptée dans `studio_submit` ou `studio_execute`.

Exemple d'appel à `studio_submit` pour un essayage, une fois les noms réels inspectés :

```json
{
  "request_id": "try-on-run-001",
  "operation": "wardrobe_review",
  "arguments": {
    "source": "asset:characters/character-packed.blend",
    "specification": {
      "schema": "cryptonyan.wardrobe-review/1",
      "armature": "ExistingRig",
      "body": "Body",
      "garments": ["Shirt"],
      "tolerance_m": 0.0001,
      "max_influences": 4,
      "captures": [{
        "armature": "ExistingRig", "action": "Run",
        "start_frame": 1, "end_frame": 31, "step_frames": 1,
        "settings": {
          "root": "Origin", "bones": ["Tip"], "loop": true,
          "motion": "in_place", "contact_space": "unknown", "contacts": []
        }
      }]
    }
  }
}
```

Cet exemple respecte le schéma ; les noms du personnage et de l’action doivent
être adaptés après inspection. Le guide MCP donne les types exacts et
[l’exemple complet](examples/animated-wardrobe.json) montre plusieurs actions.
Une phrase utilisateur ne remplace jamais ce schéma.

## Sources, destinations et reprise

Les chemins MCP sont des handles à **barres obliques `/`** :

- `asset:characters/cat.blend` : fichier sous l'asset root configuré ;
- `asset:` : racine des sources pour les recettes qui utilisent un catalogue local ;
- `work:studio/operations/try-on-run-001/output` : sortie privée de ce client.

Les chemins absolus fournis à l'outil, traversées `..` et liens symboliques dans les
handles sont refusés. Le projet Unreal vient du profil et ne peut pas être remplacé
par un champ de recette. Les plans chargés doivent correspondre au projet configuré ;
les chemins absolus imbriqués de bundles de réparation restent limités aux racines
autorisées.

Une opération écrit uniquement dans
`<workspace-client>/studio/operations/<request_id>/`. La réponse contient le statut,
le handle de sortie et les hashes des fichiers. L'agent peut réutiliser ce handle
dans l'opération suivante, puis lire les rapports ou PNG par `studio_artifact`.
Les fichiers binaires `.blend`/GLB restent des fichiers locaux.

Préférer `studio_submit` pour les opérations longues : le reçu initial est `queued`,
puis `studio_operation` suit le statut/phase avec des lectures espacées. `studio_jobs`
retrouve les identifiants ; `studio_cancel` annule les demandes en attente ou demande
l'arrêt du travail actif. `studio_execute` reste synchrone sur cette même file.
Consulter [le cycle de vie, l'annulation et les budgets](background-operations.md).

Une perte de réponse n'autorise pas un nouveau calcul : rappeler avec le **même
identifiant, la même opération et les mêmes arguments**, y compris en changeant de
submit à execute. Si le reçu terminé et ses hashes sont intacts, le résultat est
renvoyé sans exécution, même si les sources ont été retirées. Le contexte de
configuration (racines, Blender, projet) fait partie de l'identité.

Après un redémarrage, un reçu `queued`, `running` ou `cancelling` devient `interrupted`
et n'est jamais relancé automatiquement. Examiner les sorties partielles et vérifier
les éventuels anciens processus Blender après un crash avant une nouvelle tentative.
Une opération `failed`, `timed_out`, `cancelled` ou `interrupted` ne devient pas un
succès par rappel. `succeeded` signifie que le parcours s'est terminé, **pas** que
son audit est sans défaut ni qu'une adoption dans le jeu est approuvée. Lire le résultat.
Les sorties partielles restent disponibles localement pour diagnostic, hors manifeste.

Un seul service possède ce dossier. Limites : 1 024 identifiants conservés, 2 048
fichiers et 2 Gio d'artefacts par opération, plus les budgets propres à chaque module.
Il n'y a pas de suppression automatique des résultats.

## Unreal et TRELLIS

`unreal_handoff` accepte `comparison_stage`, `director_review` ou `modular_review`.
Il vérifie le plan/bundle puis génère un script Python inerte avec les chemins
explicites et un contrôle du projet actif. Lancer ce script **dans la console Python
Unreal 5.8**, après lecture. Sa création n'exécute pas le moteur et ne prouve pas le
placement, le rendu ou les poses. Le script et le dossier prévus apparaissent dans
les artefacts. Les sorties d'éditeur créées ensuite ne sont pas des résultats
d'exécution MCP et ne sont pas ajoutées rétroactivement à son manifeste.

TRELLIS est signalé comme une intégration restant à compléter avec les exports API
réels et une collecte 3D. Les outils de textures PNG ne sont pas un générateur de
mesh. Aucun autre service de génération n'est substitué implicitement.

## Évaluation et validations locales

```powershell
python -m cryptonyan_asset_studio.capabilities catalog
python -m cryptonyan_asset_studio.capabilities route 'Mon manteau traverse le corps pendant la course'
python -m cryptonyan_asset_studio.capabilities evaluate `
  'D:\Dev\loopcut\loopcut\harness\cryptonyan_routing_cases.json'
```

Les 26 cas FR/EN évaluent notre routeur lexical sur une liste étiquetée, avec
négation limitée, ambiguïté, demande vague et texte d'injection. Ce ne sont ni des
évaluations de modèle ni une preuve d'autonomie générale. Les tests vérifient aussi
le vrai protocole stdio, la préparation CPU de caméras/niveaux et un appel MCP vers
un vrai worker Blender. Les applications Claude/Codex, ComfyUI GPU et Unreal ne sont
pas exécutés dans le cloud. Voir la [checklist PC](local-pc-checklist.md).
