# Améliorer un jeu Unreal existant

La v0.12 ajoute une passerelle vers un projet Unreal déjà créé. Elle recherche les
fichiers existants, distingue les profils ComfyUI du projet des profils de textures
exécutables, et associe chaque demande de texture à une version précise d'un asset.
Le personnage, son squelette, ses animations et les niveaux existants restent les
références. Les kits et le chat générés par l'atelier créatif sont des démonstrations
optionnelles ; leur installation n'est pas nécessaire pour utiliser cette passerelle.

La v0.13 complète ce parcours avec [l'inspection dans Unreal, un plan MCP et une
copie de mesh portant une variante de matériau](unreal-material-variants.md). Le
simple inventaire de fichiers ci-dessous reste distinct de cette inspection éditeur.

## Ce qui fonctionne

- Inventaire paginé et recherche dans `Content/` et `SourceAssets/`, sans ouvrir Unreal.
- Détection des pointeurs Git LFS non téléchargés. Ils restent visibles dans
  l'inventaire, mais une demande liée à un tel fichier est refusée.
- Lecture des métadonnées de `Pipeline/comfy_profiles.json` (profils sous forme
  d'objet). Aucune commande, instruction de fichier ou workflow du jeu n'est exécuté.
- Quatre outils MCP optionnels : `project_inventory`, `project_profiles`,
  `project_texture_submit`, `project_texture_collect`. Les deux derniers nécessitent
  un catalogue de textures configuré avec `--comfy-profiles`.
- Génération réelle via le client ComfyUI existant, identifiant durable, récupération
  des PNG en bundle Material Doctor et manifeste reliant résultat et source.
- Refus de collecter pour une source modifiée ; reprise sans double soumission après
  réponse perdue. Les outils `texture_status`, `texture_jobs` et `texture_cancel`
  servent aussi pour ces demandes.

La génération utilise le prompt et le workflow configuré. **Le modèle 3D et ses UV ne
sont pas envoyés à ComfyUI** : une nouvelle image n'est donc pas automatiquement
adaptée à l'atlas d'un personnage. La surface indiquée est une intention humaine,
pas un slot de matériau vérifié par Unreal.

## Configuration Windows

Utiliser un checkout du jeu avec ses fichiers Git LFS téléchargés. Le workspace du
service doit être un dossier séparé du jeu et de ses parents, réservé à cet opérateur.
Le serveur refuse une configuration imbriquée avant de créer son workspace.

Depuis le checkout Loopcut, adapter ces exemples :

```powershell
$env:PYTHONPATH = (Resolve-Path .\scripts\addons_core).Path
$gameProject = 'C:\src\MonJeuUnreal'
py -3.13 -m cryptonyan_asset_studio.game_project $gameProject --query Lantern --limit 20
py -3.13 -m cryptonyan_asset_studio.game_project $gameProject --profiles
```

Lecture seule : ces commandes n'écrivent pas de fichier et ne lancent aucun logiciel.
Pour un agent MCP, configurer une commande stdio équivalente à :

```powershell
py -3.13 -m cryptonyan_asset_studio `
  --workspace 'C:\CryptoNyanJobs\existing-game' `
  --asset-root "$gameProject\SourceAssets" `
  --game-project $gameProject `
  --comfy-profiles 'C:\CryptoNyanProfiles\textures.json' serve
```

Cette commande laisse l'exécuteur des missions Asset Doctor en mode `mock` par
défaut ; **les outils de texture utilisent leur vrai client HTTP ComfyUI**, indépendamment
de cet exécuteur. Pour les missions Blender réelles, ajouter `--executor blender`
et `--blender 'C:\chemin\blender.exe'`. Le protocole MCP reste sur stdin/stdout.
Sans `--comfy-profiles`, seuls les deux outils de découverte du projet sont ajoutés.

Le catalogue de textures suit le [guide des profils](comfy-agent-profiles.md).
Les profils natifs 3D du jeu ne doivent pas être passés directement à cette option :
leurs paramètres et formats de sortie diffèrent. Ils apparaissent avec
`executable_by_texture_bridge: false`. Le profil PNG doit déclarer ses sorties,
ses modèles et le hash du workflow examiné. Aucun modèle n'est téléchargé ici.

## Exemple de conversation agent → outils

1. `project_inventory` :

```json
{"query":"Lantern","offset":0,"limit":20}
```

2. `project_profiles` avec `{}`. Choisir un ID de `texture_profiles`, puis une
   cible exacte renvoyée par l'inventaire. Les valeurs suivantes sont illustratives :

3. `project_texture_submit` :

```json
{
  "request_id":"garden-lantern-paper-001",
  "target":"Content/Props/Lantern.uasset",
  "surface":"Lantern / Paper slot",
  "profile":"paper-texture",
  "prompt":"Papier rouge chaud de lanterne, fibres fines, sans texte, sans ombre portée",
  "seed":42
}
```

4. `texture_status` avec `{"request_id":"garden-lantern-paper-001"}`.
5. Après succès, `project_texture_collect` avec le même identifiant.

Le résultat contient le `candidate_manifest`, la cible avec SHA-256, la surface
souhaitée, le manifeste du matériau et les reçus de génération. Tous les artefacts
sont dans le workspace externe. `applied_to_game` et `surface_verified` restent
`false`. L'agent doit présenter le résultat comme une **variante à examiner**.

Ne pas utiliser `texture_collect` pour attester le lien au jeu : cet outil générique
ne vérifie que les textures. `project_texture_collect` vérifie également la cible
avant et après le téléchargement. Il reste possible de récupérer les images avec
l'outil générique si l'asset a changé, mais leur compatibilité doit être réexaminée.

## Reprise, limites et données

- Réutiliser exactement le même ID, la même cible, la même surface et les mêmes
  paramètres après une réponse perdue. Une soumission incertaine n'est pas relancée.
- Un ID déjà utilisé par une demande de texture générique ne peut pas être récupéré
  rétroactivement pour un asset. Un nouveau checkout ou un `.uproject` modifié exige
  de réexaminer l'association ; les images déjà collectées restent conservées.
- Le workspace privé est mono-propriétaire grâce au verrou de TextureService.
  Les APIs synchrones ne doivent pas être appelées simultanément depuis des threads.
- Scan limité à 100 000 entrées sous les deux dossiers, pages de 1 à 200 résultats,
  cible de 1 octet à 512 Mio, 256 associations maximum par workspace. Chemins relatifs
  propres uniquement ; liens symboliques refusés pour les cibles, ignorés dans le scan.
- Les empreintes portent sur **le fichier ciblé**, pas sur toutes ses dépendances,
  textures externes, fichiers `.uexp`, squelette ou animations. Elles détectent une
  modification, mais ne constituent pas une sauvegarde ni un verrou de l'éditeur.
- L'inventaire donne des noms de packages `/Game/...`, pas les classes ou chemins
  d'objets internes. Les fichiers `.uasset` restent opaques ; un nom `SK_` ne prouve
  pas une classe. Les fichiers de Plugins et autres dossiers ne sont pas inventoriés.
- Ne pas versionner les inventaires, prompts ou reçus privés du jeu dans un dépôt
  public d'outillage. Aucune copie des assets du jeu n'est incluse dans Loopcut.

## Application au jeu : étape locale distincte

La passerelle n'applique pas les résultats dans les niveaux existants. La v0.13
implémente les étapes 1 à 3 ci-dessous pour des meshes et matériaux pris en charge,
avec une copie d'asset de revue, sans modifier d'acteur existant. L'exécution réelle
exige la validation locale du [nouveau guide](unreal-material-variants.md).

1. Interroger l'Asset Registry et les matériaux/slots réellement utilisés dans Unreal.
2. Créer une nouvelle instance de matériau compatible avec le parent existant,
   les conventions normales/couleurs et les UV ; ne pas écraser un matériau partagé.
3. Essayer la variante sur une copie de scène ou une sélection de revue explicite.
4. Comparer avant/après dans le jeu, contrôler rig, collisions, lisibilité et performance.
5. Adopter la variante retenue par une modification ciblée du projet.

Ne pas remplacer un personnage existant par le quadrupède de démonstration, ni
installer un deuxième système de pouvoirs pour une fonction déjà disponible.
La priorité est l'intégration aux systèmes en place.

## Validation

Les tests couvrent stdio réel en sous-processus, inventaire, LFS, confinement,
pagination, reprise après interruption, empreintes périmées et parcours MCP complet
vers un serveur HTTP simulé jusqu'au bundle Material Doctor. Les fixtures `.uasset`
sont opaques et synthétiques : ce ne sont pas des packages Unreal validés.
GPU ComfyUI, classes Unreal, rendu/UV et application dans le jeu nécessitent les
[vérifications locales](local-pc-checklist.md#0-raccorder-ton-jeu-existant-v012).
