# Mettre à jour sur Windows

Il suffit normalement de mettre à jour le dépôt. **Aucune réinstallation complète**
de Python, Blender, Unreal, ComfyUI ou des modèles n'est nécessaire pour les
évolutions Python de CryptoNyan Asset Studio. Les profils existants sont compatibles
avec v0.34. Une mise à jour du code ne lance pas de migration du projet du jeu.

## Si le dépôt a été cloné avec Git

1. Attendre la fin des opérations ou les annuler et attendre `cancelled`.
   Déconnecter le MCP CryptoNyan dans Claude/Codex et fermer Blender pour que les
   processus Python chargent tous la même version au prochain lancement.
2. Ouvrir PowerShell dans le dossier du dépôt. Adapter le chemin :

   ```powershell
   Set-Location D:\Dev\loopcut
   git remote -v
   git status
   git branch --show-current
   ```

   Le dépôt attendu est `https://github.com/swisspatate/loopcut.git`.
   Si `git status` indique des modifications, les conserver : les faire examiner
   ou les enregistrer sur une branche dédiée avant la suite. Ne pas utiliser
   `reset --hard`, `clean` ou une suppression du dossier pour débloquer la mise à jour.
3. Lorsque le dossier est propre, revenir sur `main` puis récupérer les mises à jour :

   ```powershell
   git switch main
   git pull --ff-only origin main
   ```

   Si Git refuse parce que les historiques ont divergé, arrêter cette procédure et
   faire examiner son message. `--ff-only` évite une fusion improvisée sur le PC.
   Si la branche n'existe pas localement, vérifier les branches avec `git branch -a`
   avant d'en créer une ; ne pas modifier le dépôt du jeu à sa place.
4. Reconnecter le MCP dans Claude/Codex et rouvrir Blender. Le panneau CryptoNyan
   enregistré manuellement doit être réenregistré dans cette nouvelle session :
   voir [agent-connections.md](agent-connections.md#afficher-le-panneau-dans-blender).

Conserver le dépôt au même chemin pour garder valides les lanceurs MCP existants.
S'il est déplacé, mettre à jour le profil et réexporter les fragments de connexion
avec [agent_connect](agent-connections.md), puis remplacer seulement l'entrée
CryptoNyan dans les réglages des clients.

## Vérifier la version et la connexion

Depuis le dépôt, avec le Python autonome 3.11+ déjà configuré :

```powershell
$env:PYTHONPATH = (Resolve-Path .\scripts\addons_core).Path
$pythonBinary = py -3.13 -c "import sys; print(sys.executable)"
& $pythonBinary -c "import cryptonyan_asset_studio as studio; print(studio.__version__)"
& $pythonBinary -m cryptonyan_asset_studio.agent_connect check `
  'D:\CryptoNyanWork\connection.json' --probe-mcp
```

Adapter `-3.13` au Python réellement installé et le chemin du profil existant.
Le diagnostic MCP emploie une file temporaire et ne soumet aucune opération.
Il vérifie notre serveur, pas les choix du modèle ni une génération ComfyUI.
Les nouvelles fonctions apparaissent seulement après reconnexion du MCP.

## Si un ZIP a été téléchargé

Extraire le nouveau ZIP dans un nouveau dossier, conserver l'ancien comme sauvegarde
et rétablir le chemin du dépôt utilisé par les lanceurs, ou réexporter leurs réglages.
Ne pas mélanger les anciens et nouveaux modules dans un serveur encore lancé.
Pour simplifier les prochaines mises à jour, utiliser à la place un clone séparé :

```powershell
git clone https://github.com/swisspatate/loopcut.git D:\Dev\loopcut
```

La destination doit être absente ou vide ; ne pas cloner par-dessus l'installation
existante. Réutiliser les profils et dossiers externes après ajustement des chemins.

## Ce qu'il faut conserver

- Le profil `connection.json`, les profils et workflows ComfyUI réels.
- Les sources `.blend`, les références et le projet `CryptoNyanRunUnreal`.
- Le dossier de travail des agents, ses reçus et les anciens résultats : depuis
  v0.34, de nouveaux parcours peuvent référencer des snapshots d'anciens parcours.
  Effacer cet historique invalide les résultats qui en dépendent.

L'organisation conseillée sépare `D:\Dev\loopcut`, `D:\CryptoNyanWork`, les assets
et le projet du jeu. Faire une sauvegarde de ses réglages avant une mise à jour.
Une évolution des dépendances ou du binaire Loopcut/Blender sera signalée séparément :
`git pull` met à jour les sources et ne recompile ni ne remplace un Blender installé.
