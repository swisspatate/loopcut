# Collections de textures pour le jeu existant — v0.15

Une collection prépare **1 à 16 textures candidates** avec un profil ComfyUI commun,
une direction artistique commune et une description par entrée. Chaque entrée vise
un fichier existant du jeu et une surface explicitement nommée. On peut traiter
plusieurs assets, ou plusieurs variantes du même asset avec des identifiants distincts.

Le service réutilise les profils approuvés, le prévol v0.14, les demandes liées aux
assets, la collecte PNG et Material Doctor. Il produit des candidats utilisables
par le [parcours de variantes Unreal](unreal-material-variants.md), sans modifier
les meshes, rigs, matériaux ou niveaux du projet.

**Le style commun et les seeds rendent les demandes reproductibles, pas la qualité
artistique garantie.** Les UV, l'échelle des motifs, les raccords, les atlas et la
cohérence visuelle doivent être vérifiés. Aucune véritable inférence GPU ou validation
Unreal n'a été exécutée pour ce lot dans le cloud.

## 1. Préparer un lot sans lancer de calcul

Adapter [l'exemple JSON](examples/texture-collection.json) aux vrais chemins obtenus
avec `project_inventory`, aux surfaces visées et à un profil de `texture_profiles`.
Les chemins de l'exemple sont fictifs. Le profil d'exemple reste un gabarit à configurer
avec ton installation ComfyUI ; aucun modèle n'est préinstallé par cette fonction.

Champs du document :

| Champ | Rôle |
| --- | --- |
| `schema` | `cryptonyan.texture-collection/1` |
| `collection_id` | Identifiant durable du lot, 1–40 caractères ASCII minuscules, chiffres, tiret ou underscore |
| `profile` | Un seul profil PNG/PBR configuré pour tout le lot |
| `style` | Direction artistique commune, 1–1 024 caractères |
| `seed` | Seed de collection, entier de 0 à 4 294 967 295 |
| `items` | 1–16 entrées avec `id`, `target`, `surface`, `description` |

`target` est relatif au projet : `.uasset`, `.blend`, `.fbx` ou `.glb` sous `Content`
ou `SourceAssets`. Les pointeurs Git LFS non téléchargés sont refusés. `surface`
décrit l'objet/slot envisagé ; ce texte n'atteste pas l'existence du slot dans Unreal.
L'inspection éditeur reste nécessaire avant de préparer une variante Unreal.

Le prompt effectif est exactement `style + "\n\n" + description`. Le modèle,
workflow, prompt négatif, résolution, nombre d'images et canaux viennent du profil.
Une seed de 32 bits est dérivée de la seed de collection et de l'ID d'entrée par
SHA-256. Réordonner les entrées ne change pas leurs seeds ; changer le profil ou
l'environnement GPU peut changer les images malgré une seed identique.

Le plan enregistre les empreintes des fichiers cibles, l'identité du checkout,
le contrat du profil, les prompts, seeds et IDs de demandes dérivés. Il est immuable.
Le même ID avec le même document rend le plan existant ; des paramètres différents
sont refusés. Modifier volontairement une collection exige un nouvel ID. Ne jamais
utiliser ce mécanisme pour contourner une soumission incertaine.

## 2. Utilisation avec l'agent MCP

Configurer le serveur avec `--game-project` et `--comfy-profiles` comme dans
[la passerelle projet](existing-project.md). Les cinq nouveaux outils sont :

| Outil | Arguments | Effet |
| --- | --- | --- |
| `project_collection_plan` | `{"specification": DOCUMENT_JSON}` | Valide et enregistre le plan, sans HTTP ni calcul GPU |
| `project_collection_status` | `{"collection_id":"garden-stone-001"}` | Lit les reçus localement, sans polling ni validation des octets des résultats |
| `project_collection_advance` | mêmes arguments | Vérifie les sources, puis soumet au plus une nouvelle demande après prévol, ou consulte la demande en cours |
| `project_collection_collect` | mêmes arguments | Récupère au plus un nouveau résultat et publie l'index si le lot est complet |
| `project_collections` | `{}` | Retrouve les IDs conservés après une perte de contexte |

Le serveur expose 22 outils lorsque missions, textures et projet sont configurés.
Les configurations sans projet ou sans textures conservent leurs outils existants.

Parcours à suivre :

1. Créer le plan, examiner les prompts, cibles et seeds retournés.
2. Appeler `project_collection_advance`.
3. Si `action=submitted`, conserver l'ID retourné. Espacer les appels suivants de
   quelques secondes ; `advance` consulte alors cette demande sans refaire de POST.
4. Si `action=collect`, appeler `project_collection_collect`.
5. Après `action=collected`, continuer avec `advance` pour l'entrée suivante.
6. Lorsque `index_file` est renseigné, le lot possède son index vérifié. Un dernier
   `collect` peut aussi vérifier à nouveau les candidats et rendre cet index hors ligne.

Il n'y a pas de boucle de fond : **arrêter d'appeler `advance` arrête les nouvelles
soumissions**. Une génération déjà envoyée continue dans ComfyUI. Pour une tâche
encore en attente, utiliser `texture_cancel` avec l'ID de demande retourné ; pour un
calcul déjà actif, utiliser l'interface ComfyUI. Aucun `/interrupt` global n'est envoyé.

## 3. Gestion des blocages et reprise

- `preflight_blocked` : lire le diagnostic. Cette première version exige le statut
  `compatible` avant chaque nouvelle soumission. Les statuts `needs_review`, `blocked`
  et `unavailable` ne sont pas contournés automatiquement. Les workflows personnalisés
  non interprétés restent utilisables individuellement après examen via le parcours existant.
- `wait_or_inspect` : regarder `status.status`. `queued` et `running` demandent
  d'attendre. `failed`, `cancelled` et `unknown` demandent une inspection ; la suite
  du lot n'est pas lancée automatiquement et aucun ID de remplacement n'est créé.
- `manual_inspection_required` : un reçu est incomplet ou ambigu. Conserver le
  workspace et examiner ComfyUI avant toute action. Ne pas supprimer les reçus.
- `advance_or_inspect` lors de la collecte : cette entrée n'est pas encore soumise,
  ou son état local ne permet pas une collecte sûre.
- Asset, descripteur de projet ou profil modifié : l'opération échoue. Les sorties
  partielles restent disponibles pour examen. Un profil modifié bloque les nouvelles
  demandes ; les demandes déjà soumises restent récupérables depuis leurs reçus.

Une intention de soumission est écrite avant tout POST. Après redémarrage, les
reçus existants empêchent un second envoi. Une réponse perdue ne prouve pas que le
calcul a échoué : si l'historique confirme plus tard son succès, on peut récupérer
ce même prompt. Un reçu manquant dans un dossier de demande existant impose une
inspection, sans resoumission automatique.

Cette garantie suppose de conserver le workspace privé et ses reçus. Ne pas déplacer,
effacer ou restaurer partiellement les dossiers pour reprendre un lot. Un seul service
possède le workspace à la fois ; la CLI et le MCP ne doivent pas l'ouvrir simultanément.
Éviter aussi les modifications concurrentes des assets sources pendant ces opérations.

## 4. Fichiers produits et utilisation dans Unreal

Sous le workspace **textures** :

```text
collections/collection-garden-stone-001/
  plan.json                    plan et empreinte
  item-rock-wet.intent.json    intention durable avant soumission
  item-wall-moss.intent.json
  item-wall-dry.intent.json
  index.json                   seulement lorsque tous les candidats sont collectés
requests/col-.../               jobs ComfyUI et bundles Material Doctor existants
asset-bindings/col-....json     liaison à l'asset source
asset-bindings/col-....candidate.json
```

L'index relie chaque entrée à sa source, sa surface, sa seed, son ID de demande,
son candidat et son `material.json`. Les octets des résultats et les sources sont
revérifiés avant publication. Un candidat ou index corrompu est conservé et refusé,
sans écrasement. Le statut local seul ne certifie pas cette intégrité.

Utiliser chaque `request_id` avec `project_material_plan`, l'inspection Unreal de
son asset, le slot réel et les bindings explicites. Ce parcours crée des variantes
sur copies pour revue. Le lot ne place rien dans les niveaux et ne remplace aucun
matériau automatiquement.

Les plans contiennent des noms privés et les candidats des chemins locaux : garder
ces données sur le PC. L'index n'est pas un paquet portable indépendant du workspace.
Les indicateurs `visual_consistency_verified`, `model_provenance_verified`,
`distribution_approved` et `applied_to_game` restent `false`.

## 5. Alternative PowerShell

Fermer d'abord le service MCP propriétaire du même workspace. Adapter les chemins :

```powershell
$env:PYTHONPATH = (Resolve-Path .\scripts\addons_core).Path
$collectionArgs = @(
  '--project', 'D:\Games\CryptoNyanRunUnreal',
  '--catalog', 'D:\CryptoNyanWork\profiles\profiles.json',
  '--workspace', 'D:\CryptoNyanJobs\existing-game\textures'
)
py -3.13 -m cryptonyan_asset_studio.texture_collections @collectionArgs plan .\my-collection.json
py -3.13 -m cryptonyan_asset_studio.texture_collections @collectionArgs advance garden-stone-001
py -3.13 -m cryptonyan_asset_studio.texture_collections @collectionArgs status garden-stone-001
# Après confirmation du succès dans advance / texture_status :
py -3.13 -m cryptonyan_asset_studio.texture_collections @collectionArgs collect garden-stone-001
py -3.13 -m cryptonyan_asset_studio.texture_collections @collectionArgs list
```

`--workspace` est ici le dossier **textures**, et non son parent utilisé par la CLI
principale MCP. Un workspace situé dans le projet est refusé avant sa création.
Code retour 0 signifie qu'un rapport d'opération a été produit : lire son `action`,
qui peut signaler une attente ou un prévol bloqué. Une erreur lève un code retour 2.

## Limites et validation locale

32 collections par workspace, 16 entrées chacune, 256 demandes de textures conservées
au total. Un plan vérifie la capacité disponible sans réserver un quota GPU global.
Une collection n'envoie pas l'entrée suivante avant collecte de la précédente ;
plusieurs collections ou jobs manuels peuvent néanmoins partager la queue ComfyUI.
Les limites de collecte existantes restent appliquées **par demande**.

Chaque fichier source est limité à 512 Mio, avec 1 Gio de fichiers distincts par lot.
Les sources sont rehachées pendant les opérations : les gros lots peuvent prendre
du temps. Le prévol exige une installation correspondant au profil prévu, mais
n'atteste pas les octets des poids ni la mémoire GPU nécessaire. Ni LoRA de style,
ControlNet, image de référence, adaptation UV ou comparaison visuelle ne sont ajoutés
automatiquement ; ils demandent des profils/adaptateurs adaptés et une validation dédiée.

Sur le PC, commencer par deux petites textures sur des copies de travail :

- vérifier que `plan` n'ajoute rien à la queue ;
- lancer la première entrée, redémarrer le service, vérifier le même prompt ID et
  l'absence de second POST pour cette entrée ;
- collecter puis lancer la seconde, vérifier les hashes et l'index final ;
- comparer palette, échelle des motifs, UV et normales sur les copies Unreal ;
- noter modèles, versions, seed, temps et pic VRAM ;
- tester un checkpoint absent dans une copie du profil et confirmer le blocage
  avant soumission ; ne pas provoquer de corruption dans les reçus de production.

Voir aussi la [checklist locale](local-pc-checklist.md#6-comfyui-et-rtx-5080).
