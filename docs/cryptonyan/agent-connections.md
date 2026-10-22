# Connexions Claude Code, Codex et ComfyUI — v0.23

Depuis v0.38, reconnecter le MCP expose project_collection_review et
project_collection_review_artifact quand textures/projet sont configurés. La
[galerie locale](collection-review.md) utilise les collections existantes ; aucun
champ de profil de connexion ni modèle supplémentaire n'est nécessaire.

Depuis v0.37, les [collections de textures](texture-collections.md) acceptent
preparation_id par entrée pour un profil à reference_slots. Reconnecter le MCP
pour lire le schéma et les consignes à jour ; les outils existants, profils de
connexion et anciens plans restent valides. Aucun nouveau service n'est requis.

Depuis v0.36, les [références choisies par l'agent](comfy-reference-preparations.md)
ajoutent texture_reference_prepare/preflight/submit et, avec le projet configuré,
project_texture_reference_submit. Reconnecter le MCP ; configurer reference_slots
et le vrai input_root dans le catalogue ComfyUI pour utiliser ce parcours.
Les anciens catalogues et profils de connexion restent compatibles.

Depuis v0.35, un profil ComfyUI configuré expose texture_inspect et texture_image,
ainsi que leurs variantes project_texture_inspect/project_texture_image si le
projet est configuré. Reconnecter le MCP ; les profils existants restent valides.
Voir la [revue des cartes et leurs chemins Studio](comfy-texture-review.md).

Pour les prochaines installations : [mettre à jour sur Windows](updating-windows.md),
sans réinstaller Blender, ComfyUI ou les modèles.
Depuis v0.34, reconnecter le MCP expose studio_workflow_inspect,
studio_workflow_step_artifact et studio_workflow_fork pour la
[réutilisation explicite des snapshots](workflow-reuse.md). Les profils restent valides.

Depuis v0.33, [les parcours Studio](studio-workflows.md) ajoutent
studio_workflow_template et workflow_run sur la file existante. Reconnecter le
serveur ; aucun nouveau champ, modèle ou compte n'est nécessaire.

Depuis v0.32, les [opérations longues](background-operations.md) peuvent être
soumises en arrière-plan, suivies et annulées. Reconnecter le serveur pour découvrir
`studio_submit`, `studio_cancel` et `studio_jobs` ; aucun champ de profil à ajouter.
La fermeture normale annule le travail actif ; une interruption brutale reste à examiner.

Depuis v0.31, le serveur fournit le [catalogue et les consignes de choix des outils](agent-routing.md),
avec des opérations MCP supplémentaires. Les profils existants restent valides ;
redémarrer/reconnecter le serveur pour découvrir les nouveaux outils.

Le panneau **CryptoNyan → Connexions des agents** prépare la connexion de ton agent
externe aux outils existants du fork. Il enregistre un profil local, copie les
réglages MCP au format Claude Code ou Codex et teste la liaison sans lancer de
mission ni de génération. Une interface en ligne de commande fournit les mêmes fonctions.

Cette version reprend l'idée du parcours « Connect MCP » de Mixar, avec une
implémentation indépendante qui réutilise notre serveur. Aucun compte Mixar,
serveur Mixar, jeton copié ou modèle supplémentaire n'est nécessaire.
L'étude et les prochains portages sont suivis dans [mixar-integration.md](mixar-integration.md).

## Installation Windows, y compris sur D:

Conserver le dépôt complet, par exemple `D:\Dev\loopcut`, et installer Python
**3.11 ou supérieur**. Le Python de lancement est un `python.exe` autonome, pas
`blender.exe`, `py.exe` ou un wrapper `.cmd`. Aucun paquet pip supplémentaire.
Le dossier de travail, les sources à traiter et le projet du jeu doivent respecter
les séparations décrites ci-dessous. Les chemins avec espaces sont pris en charge.

Exemple PowerShell à adapter aux installations réelles :

```powershell
Set-Location D:\Dev\loopcut
$env:PYTHONPATH = (Resolve-Path .\scripts\addons_core).Path
$pythonBinary = py -3.13 -c "import sys; print(sys.executable)"

& $pythonBinary -m cryptonyan_asset_studio.agent_connect init `
  'D:\CryptoNyanWork\connection.json' `
  --workspace 'D:\CryptoNyanWork\agent-jobs' `
  --asset-root 'D:\CryptoNyanAssets' `
  --blender 'D:\Applications\Blender\blender.exe'
```

Créer le dossier des assets avant cette commande. Les `.blend` à traiter doivent
être sauvegardés et autonomes, comme pour les missions existantes. Pour un test sans
Blender, remplacer `--blender ...` par `--executor mock` et utiliser le dossier
`docs\cryptonyan\examples\assets` du dépôt comme `--asset-root`.

Options facultatives de `init` :

- `--comfy-profiles 'D:\CryptoNyanWork\comfy\profiles.json'` : notre catalogue
  [de profils approuvés](comfy-agent-profiles.md), pas un workflow brut ou un export
  graphique ComfyUI. Il doit déjà être configuré avec ses workflows et hashes.
- `--game-project 'D:\Jeux\CryptoNyanRunUnreal'` : dossier contenant le `.uproject`.
- Depuis v0.24, `--reference-root 'D:\CryptoNyanWork\references'` expose les
  [tableaux de références](reference-boards.md) en lecture seule, avec leurs PNG.
- `--replace` : mettre à jour un profil CryptoNyan existant. Un fichier Claude/Codex
  ou un autre JSON n'est jamais remplacé par cette commande.

Le dossier des assets peut appartenir au projet du jeu. Le dossier de travail doit
être séparé de ces sources : aucune inclusion dans un sens ou dans l'autre.

## Configurer les agents

```powershell
& $pythonBinary -m cryptonyan_asset_studio.agent_connect export `
  'D:\CryptoNyanWork\connection.json' --client claude

& $pythonBinary -m cryptonyan_asset_studio.agent_connect export `
  'D:\CryptoNyanWork\connection.json' --client codex
```

- **Claude Code** : ajouter l'entrée `cryptonyan` au dictionnaire `mcpServers` du
  fichier `.mcp.json` du projet choisi. Préserver les entrées existantes.
- **Codex** : ajouter la table `[mcp_servers.cryptonyan]` au `config.toml` de ton
  profil Codex habituel. Si cette table existe déjà, mettre à jour cette entrée
  plutôt que créer un doublon.

Les fragments contiennent le chemin absolu de Python, le lanceur et le profil.
Ils fonctionnent sans répertoire courant particulier et sans `PYTHONPATH`, grâce
au lancement isolé `python -I`. Reconnecter ensuite le MCP dans l'agent ; accepter
son éventuelle demande de confiance suivant ses réglages habituels.

Le générateur **n'écrit pas dans les configurations des agents**, ne lit pas leurs
comptes et ne vérifie pas leur authentification. Un diagnostic MCP réussi prouve
le démarrage de notre serveur, pas la connexion effective depuis Claude/Codex.

Claude utilise `agent-jobs/mcp-claude`, Codex `agent-jobs/mcp-codex`. Les files et
reçus sont distincts ; les deux applications peuvent donc se connecter ensemble.
Une seconde connexion du **même client au même profil** reste refusée si elle
essaie de posséder la même file. Éviter les doubles connexions projet/utilisateur.
Une demande envoyée par les deux clients reste deux demandes indépendantes ; leur
séparation ne fournit pas de déduplication globale ni d'arbitrage GPU.

Le client Codex externe envoie directement ses missions à l'exécuteur Blender :
ce parcours n'ajoute pas un deuxième tour de modèle Codex. L'adaptateur expérimental
Claude → Codex → Blender reste disponible par sa [configuration existante](codex-adapter.md).

## Afficher le panneau dans Blender

Dans la console Python de Blender (`Shift+F4`), exécuter, avec ton chemin réel :

```python
import sys
sys.path.insert(0, r"D:\Dev\loopcut\scripts\addons_core")
import cryptonyan_asset_studio
cryptonyan_asset_studio.register()
```

Revenir à la vue 3D (`Shift+F5`), ouvrir la barre latérale (`N`), onglet
**CryptoNyan**. Choisir le fichier `connection.json`, puis **Charger le profil**.
On peut aussi remplir les chemins directement et **Enregistrer le profil**.
Choisir Claude Code ou Codex et **Copier la configuration de l'agent**.

**Tester MCP et ComfyUI** lance un diagnostic en arrière-plan pour garder
l'interface disponible. Une modification des champs invalide le résultat affiché.
Les réglages sont conservés dans le JSON ; recharger ce profil à la prochaine
session. L'enregistrement du panneau est volontaire et limité à la session Blender.
Pour le retirer : `cryptonyan_asset_studio.unregister()`.

Ce panneau n'est pas un ZIP autonome : le dépôt contient aussi les inspecteurs
Loopcut réutilisés. Importer le package seul n'enregistre pas de panneau et ne lance
pas de serveur. Le MCP traite des fichiers dans des workers isolés ; il ne pilote
pas encore la scène actuellement ouverte ou les clics du viewport.

## Diagnostic et portée des résultats

```powershell
& $pythonBinary -m cryptonyan_asset_studio.agent_connect check `
  'D:\CryptoNyanWork\connection.json' --probe-mcp --probe-comfy
```

Sans les options `--probe-*`, seuls les chemins et configurations locales sont lus.

| Vérification | Ce qu'elle établit | Ce qu'elle ne valide pas |
| --- | --- | --- |
| Configuration | Chemins présents, séparation des dossiers, catalogue approuvé lisible | Droits futurs, modèles chargés, exécution Blender |
| MCP | Initialisation, catalogue exact des outils et ping dans un vrai sous-processus | Application Claude/Codex, abonnement, tour de modèle |
| ComfyUI | Réponse structurée à `GET /system_stats` sur l'adresse locale configurée | Inférence GPU, compatibilité du workflow, qualité de texture |

Le test MCP utilise **un dossier temporaire**, même si une file de production existe
ou est active. Il n'ouvre pas cette file : son démarrage pourrait sinon reprendre
des missions en attente. Il envoie seulement `initialize`, la notification
d'initialisation, `tools/list` et `ping`, puis ferme le processus. Il ne lance ni
Blender, ni Codex, ni inférence. Le serveur réel, lancé par un client, conserve son
comportement habituel de reprise des missions.

L'état global `checked` signifie que les vérifications demandées ont abouti ; lire
aussi chaque statut `not_tested` / `not_configured`. `blocked` indique un problème.
La sonde ComfyUI réutilise les restrictions loopback de l'adaptateur et ne soumet
aucun prompt. Pour tester un workflow, utiliser ensuite `texture_preflight`, puis
une petite génération réelle contrôlée depuis l'agent.

## Validation locale restante

Voir la [checklist centralisée](local-pc-checklist.md), section v0.23. Le cloud teste
le vrai protocole stdio et l'enregistrement/opérateurs du panneau dans Blender
Linux sans interface graphique. Le presse-papiers système, le dessin et la modalité
du panneau, les applications Claude/Codex Windows et ComfyUI GPU restent à valider
sur ton PC. Aucun résultat Unreal n'est déduit de ce diagnostic.
