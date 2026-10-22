# Textures à la demande depuis les agents — v0.10

Un agent connecté au serveur MCP peut choisir un profil ComfyUI, demander une
texture, suivre le calcul, puis récupérer un matériau compatible avec Material
Doctor, les copies Blender, les variantes et les aperçus PBR du monde.

```text
Claude Code / client Codex connecté au MCP
  → texture_profiles : modèles et workflows configurés
  → texture_preflight : diagnostic du profil avec le prompt et la seed (v0.14)
  → texture_submit : profil + description + seed + identifiant de demande
  → texture_status : queued / running / succeeded / failed / cancelled / unknown
  → texture_collect : PNG contrôlés + material.json + reçus de génération
  → texture_inspect / texture_image : revue des cartes collectées et chemins Studio (v0.35)
  → pipeline Blender existant : copie, publication GLB, variantes, aperçu du monde
```

Depuis v0.36, les [préparations de références](comfy-reference-preparations.md)
permettent aussi à l'agent de choisir des PNG pour les slots déclarés par l'opérateur.
Le parcours devient texture_reference_prepare → texture_reference_preflight →
texture_reference_submit, ou project_texture_reference_submit pour le jeu existant.
Depuis v0.37, les [collections](texture-collections.md) acceptent une préparation
différente par entrée : préparer les sélections, puis renseigner preparation_id
sur toutes les entrées d'un lot utilisant un profil à slots.

Les douze outils de textures sont optionnels depuis v0.36. Sans `--comfy-profiles`,
les outils de mission, de découverte et Studio restent disponibles ; les outils de
textures ne sont pas ajoutés. Cette extension ne modifie pas les agents natifs Loopcut
et n'ajoute pas d'appel autonome ComfyUI au worker Blender ou au protocole natif
Codex. C'est le client orchestrateur connecté au MCP qui appelle ces outils.

Après collecte, suivre la [revue hors ligne](comfy-texture-review.md) : dimensions,
canaux, provenance déclarée, images natives et chemins vérifiés pour les étapes
Studio existantes. Pour un candidat lié au projet, préférer les variantes
project_texture_inspect/project_texture_image qui recontrôlent les sources.

## Préparer les profils sur ton PC

Il n'est pas nécessaire de choisir les modèles pour installer le code. Le catalogue
peut commencer avec `"profiles": []`. Pour générer, il faut ensuite un workflow
fonctionnel dans ton installation ComfyUI locale, exporté au **format API**.

Un profil fixe le graphe, le checkpoint, les LoRA éventuelles, les dimensions, le
nombre d'images, les étapes, le prompt négatif et les nœuds de sortie. L'agent ne
peut changer que les entrées textuelles explicitement déclarées et la seed, ainsi
que les images des `reference_slots` si l'opérateur en a configuré.
Plusieurs profils permettent de proposer plusieurs modèles/workflows/résolutions,
par exemple `roche-512`, `metal-1024` ou `sol-pbr`. Ces noms ne désignent aucun modèle
préinstallé. Les fichiers du catalogue restent sous ton contrôle local.

L'exemple fourni contient un graphe de base avec les nœuds standards ComfyUI. Il
nécessite un checkpoint compatible avec `CheckpointLoaderSimple`, `CLIPTextEncode`,
`KSampler` et `VAEDecode`. Il ne convient pas automatiquement aux familles de modèles
utilisant d'autres chargeurs ou encodeurs. Aucun modèle ni custom node n'est téléchargé.
Le nom de checkpoint et le hash sont volontairement des placeholders invalides.

Dans PowerShell, depuis le checkout complet :

```powershell
$env:PYTHONPATH = (Resolve-Path .\scripts\addons_core).Path
$work = Join-Path $env:LOCALAPPDATA 'CryptoNyanComfy'
New-Item -ItemType Directory -Force "$work\profiles" | Out-Null
Copy-Item .\docs\cryptonyan\examples\comfy-texture-profiles.json "$work\profiles\profiles.json"
Copy-Item .\docs\cryptonyan\examples\comfy-texture-workflow-api.json "$work\profiles\comfy-texture-workflow-api.json"
```

Éditer le workflow : renseigner le vrai checkpoint, ajuster les dimensions/paramètres,
vérifier le graphe dans ComfyUI. Ou remplacer cet exemple par ton export API et
adapter les bindings du profil. Le hash approuve le graphe complet, y compris ses
modèles et nœuds ; recalculer ce hash seulement après avoir vérifié les modifications :

```powershell
$workflowPath = "$work\profiles\comfy-texture-workflow-api.json"
$hash = py -3.13 -c "import json,sys; from cryptonyan_asset_studio.comfyui_adapter import workflow_digest; print(workflow_digest(json.load(open(sys.argv[1],encoding='utf-8-sig'))))" $workflowPath
$catalog = Get-Content "$work\profiles\profiles.json" -Raw | ConvertFrom-Json
$catalog.profiles[0].workflow_sha256 = $hash.Trim()
$catalog | ConvertTo-Json -Depth 30 | Set-Content -Encoding utf8 "$work\profiles\profiles.json"
py -3.13 -m cryptonyan_asset_studio.comfy_profiles "$work\profiles\profiles.json"
```

La dernière commande valide les fichiers, hashes et bindings **hors ligne**. Le
[diagnostic v0.14](comfy-preflight.md) interroge ensuite les nœuds et choix exposés par
ComfyUI ; il ne certifie pas l'exécution. Tester le graphe dans ComfyUI avant le
premier calcul de production. Le hash n'isole pas le code
des custom nodes : utiliser des nœuds et une installation locale de confiance.

Chaque déclaration `models` a les champs `name`, `sha256`, `license`, `attribution`.
Mesurer le hash des poids avec `Get-FileHash -Algorithm SHA256`. Ces informations sont
déclaratives ; l'API n'atteste pas les poids exécutés. Tous les résultats conservent
`model_provenance_verified=false` et `distribution_approved=false`.

## Connecter le serveur MCP

Démarrer ComfyUI sur `127.0.0.1:8188`. Le serveur MCP utilise le même PC ; les
adresses distantes, proxys et redirections ne sont pas pris en charge.

Ajouter ces arguments à la configuration MCP de Claude Code ou de ton client Codex.
Exemple de fichier `.mcp.json` pour Claude Code, avec tes chemins absolus réels :

```json
{
  "mcpServers": {
    "cryptonyan": {
      "command": "C:\\Python313\\python.exe",
      "args": [
        "-m", "cryptonyan_asset_studio",
        "--workspace", "D:\\CryptoNyanWork\\bridge",
        "--asset-root", "D:\\CryptoNyan\\Assets",
        "--executor", "blender",
        "--blender", "C:\\Tools\\Loopcut\\blender.exe",
        "--comfy-profiles", "D:\\CryptoNyanWork\\profiles\\profiles.json",
        "serve"
      ],
      "env": {"PYTHONPATH": "D:\\Dev\\loopcut\\scripts\\addons_core"}
    }
  }
}
```

Placer le workspace hors du dossier des assets. Le catalogue ci-dessus doit être
copié à l'emplacement indiqué, ou son chemin remplacé par celui de `$work\profiles`.
Le client lance le processus stdio ; ne pas lancer un second serveur sur le même
workspace. Le catalogue est chargé au démarrage : redémarrer le serveur après édition.

## Exemple de conversation et appels

Demande possible : « Consulte les profils, puis génère une base color de roche
volcanique stylisée avec `texture-base-color`, seed 42. Attends le résultat et
récupère le matériau pour ma plateforme. »

| Outil | Arguments | Résultat |
| --- | --- | --- |
| `texture_profiles` | `{}` | Profils disponibles, descriptions, hashes, modèles déclarés, canaux |
| `texture_preflight` | `{"profile":"texture-base-color","prompt":"Stylized volcanic rock, orthographic surface, uniform lighting, no text","seed":42}` | Diagnostic statique `compatible`, `blocked`, `needs_review` ou `unavailable` ; aucun calcul |
| `texture_submit` | `{"profile":"texture-base-color","prompt":"Stylized volcanic rock, orthographic surface, uniform lighting, no text","seed":42,"request_id":"lava-platform-001"}` | ID de demande, ID ComfyUI, état de soumission |
| `texture_status` | `{"request_id":"lava-platform-001"}` | État observé côté ComfyUI |
| `texture_collect` | `{"request_id":"lava-platform-001"}` | Chemins du matériau et des reçus, hashes des fichiers |
| `texture_jobs` | `{}` | Demandes persistantes, récupération après perte de contexte |
| `texture_cancel` | `{"request_id":"lava-platform-001"}` | Suppression ciblée demandée si encore en attente |

La soumission retourne sans attendre le GPU. Espacer les appels de suivi (par exemple
2–5 secondes) ; ne collecter qu'après succès. Le service n'a pas de boucle autonome
de polling ni de deadline GPU. Chaque opération HTTP garde le timeout de 10 secondes
du client existant ; une collecte de plusieurs images peut prendre plus longtemps.

Le prompt contient 1–4096 caractères ; la seed est un entier non signé de 64 bits.
Pour les clients JSON utilisant des nombres JavaScript, préférer une seed de 32 bits
afin d'éviter les arrondis. L'identifiant de demande contient 1–64 caractères ASCII
alphanumériques, tirets ou underscores, et commence par un caractère alphanumérique.

Réutiliser **le même identifiant et les mêmes paramètres** après une réponse perdue.
Cela consulte le reçu sans refaire de POST, même après redémarrage ou modification
du catalogue. Des paramètres différents avec le même ID sont refusés. Une nouvelle
variante demande un nouvel ID. Si `submission=uncertain`, inspecter l'historique/la
queue et le reçu avant toute nouvelle demande : l'absence de réponse ne prouve pas
l'absence de calcul. Une interruption avant création du reçu HTTP peut nécessiter
une inspection manuelle ; aucune resoumission automatique n'est faite.

L'annulation vise uniquement le prompt en attente. Une course vers l'état running
reste possible ; la réponse ne certifie pas l'annulation. Pour un calcul déjà lancé,
utiliser ComfyUI. Aucun appel global `/interrupt` n'est émis.

## Matériaux récupérés et reprise

Les résultats sont écrits sous
`<workspace>/textures/requests/<request_id>/result/` :

- `images/` : PNG originaux et `generation.json` (graphe réellement soumis, seed,
  modèles déclarés, nœuds et indices des sorties, hashes).
- `material/` : canaux copiés avec leurs noms et `material.json`, directement
  utilisable par [le pipeline PBR](material-pipeline.md#3-material-doctor-and-blender-copy).
- `texture.json` : identité du profil, hash du template approuvé, correspondance
  des canaux et inventaire des fichiers/hashes.

`outputs` associe chaque canal à `[node_id, image_index]`, par exemple
`{"base_color":["9",0],"roughness":["12",0],"normal":["15",0]}`. Les sorties doivent
être distinctes et réellement produites par ton workflow. La base color est requise ;
roughness, metallic et normal sont optionnelles. On ne transforme jamais implicitement
une image couleur en roughness ou en normale. Les normales doivent être OpenGL +Y.

Le client conserve ses limites : 16 PNG maximum, 32 MiB par image, 128 MiB au total,
RGB/RGBA 8 bits non entrelacé, au plus 4096×4096, mêmes dimensions pour les canaux PBR.
Il collecte toutes les sorties PNG sauvegardées du graphe, puis sélectionne les
canaux déclarés. Éviter les sorties de debug inutiles dans les profils.

La collecte est préparée dans un dossier temporaire puis publiée par renommage.
Un nouvel appel retourne les fichiers existants après vérification de leurs hashes,
même hors ligne. Une corruption échoue sans écrasement. Après un arrêt brutal, des
dossiers `.collect-*` incomplets peuvent rester : les inspecter et les nettoyer
manuellement ; ils ne sont jamais annoncés comme résultat final.

Chaque workspace est privé, avec un seul propriétaire, au plus 256 demandes conservées
et aucun nettoyage automatique. À capacité, fermer le service, archiver le workspace
avec ses reçus, puis choisir un nouveau workspace. Les IDs ne sont idempotents qu'au
sein de leur workspace : ne pas changer de workspace pour contourner une soumission
incertaine. Le catalogue est limité à 32 profils et 8 MiB de templates.

## Validations et prochaines améliorations

Les tests couvrent les limites, hashes, paramètres autorisés, reprise, incertitude,
annulation, canaux, corruption et le trajet réel stdio MCP → HTTP loopback → matériau
avec un serveur de test scripté. **Aucune inférence ComfyUI/GPU n'est simulée comme
une validation réelle de modèle.** Le test réseau est obligatoire en CI ; le sandbox
local peut explicitement l'ignorer s'il interdit les sockets.

Sur ton PC, suivre la [checklist centralisée](local-pc-checklist.md#6-comfyui-et-rtx-5080).
L'application à la scène Blender reste une étape explicite du pipeline existant.
Les [variantes Unreal v0.13](unreal-material-variants.md) offrent un parcours distinct
avec inspection éditeur, bindings explicites et copie du mesh ; leur validation
réelle sur PC reste requise. L'import générique de GLB texturés garde sa limite séparée.

Le [diagnostic via `/object_info`](comfy-preflight.md) est livré en v0.14. Pistes
suivantes : catalogue avec miniatures, détecteur de coutures, mesure VRAM/temps et
sélection du profil selon le budget. Les [collections v0.15](texture-collections.md)
ajoutent les lots explicites avec style commun pour les assets du jeu, via cinq
outils `project_*` lorsque `--game-project` est aussi configuré.
