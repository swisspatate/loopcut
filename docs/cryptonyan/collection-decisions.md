# Choix et notes sur les textures — v0.39

Après une [galerie de lot](collection-review.md), l'agent peut conserver les choix
**à retenir**, **à retravailler** ou **à écarter** avec une note par texture. Les
enregistrements restent locaux, liés aux hashes de la galerie, des candidats et
des cartes. Aucune texture n'est générée, téléchargée ou appliquée.

## Depuis Claude ou Codex

Mettre à jour le checkout puis reconnecter le MCP. Les services textures et projet
doivent être configurés ; les anciens profils, collections et galeries restent
compatibles. Exemple de demande : « Note que je veux garder le manteau, mais
retravailler la pierre pour réduire ses reflets. » L'agent retrouve les vrais IDs
avec `project_collections` et `project_collection_review`, puis lit les images.
Une décision vise uniquement une entrée **collectée dans cet instantané**.

`project_collection_review_decide` reçoit :

```json
{
  "collection_id": "jade-assets-001",
  "review_id": "review-001",
  "decision_id": "feedback-001",
  "feedback": {
    "source": "user_reported",
    "supersedes": null,
    "items": [
      {"item_id": "coat", "choice": "keep", "notes": "Conserver la palette."},
      {"item_id": "stone", "choice": "revise", "notes": "Réduire les reflets."}
    ]
  }
}
```

Ces IDs sont illustratifs : utiliser ceux des résultats réels. Les choix possibles
sont `keep`, `revise`, `discard`. Le champ `notes` est obligatoire mais peut être
vide, avec au plus 1 024 caractères ; 1 à 16 entrées distinctes sont acceptées.
Chaque identifiant suit les mêmes règles que le lot : 1–40 caractères ASCII
minuscules, chiffres, tiret ou underscore, avec un premier caractère alphanumérique.

`source=agent_recommendation` indique l'avis de l'agent. `user_reported` transcrit
un choix réellement communiqué par l'utilisateur ; l'agent ne doit jamais en
inventer un. Cette attribution est déclarative : aucun des deux modes ne prouve
une approbation humaine authentifiée. Les sorties gardent
`human_approval_verified=false` et `adoption_authorized=false`.

Pour retrouver les IDs et les remplacements, appeler
`project_collection_review_decisions` avec `collection_id` et `review_id`.
La liste expose des résumés sans les notes. Pour les lire avec les empreintes
des candidats et canaux, appeler `project_collection_review_decision` en ajoutant
`decision_id`. Ces lectures revérifient la galerie, les résultats et les sources
actuelles du jeu. Elles ne contactent pas ComfyUI.

## Changer un choix et reprendre après déconnexion

Après une réponse perdue, répéter **le même `decision_id` et les mêmes arguments**.
Le service retrouve l'enregistrement ; des arguments différents sont refusés.
Les fichiers existants ne sont jamais écrasés. Les IDs sont propres à une revue.

Pour remplacer explicitement un choix, utiliser un nouvel ID et renseigner
`supersedes` avec l'ID actif à remplacer. Le nouvel enregistrement doit couvrir
exactement les mêmes entrées et avoir la même `source`. L'ordre des entrées peut
changer ; leurs choix et notes peuvent changer. L'ancien reste consultable avec
`superseded=true`. Sa reprise retourne aussi ce statut actuel. Un prédécesseur
déjà remplacé, une branche concurrente ou un cycle sont refusés.

Des enregistrements indépendants peuvent se contredire, notamment entre l'agent
et l'utilisateur. Le service conserve ces avis sans choisir automatiquement le
dernier, ni fusionner leurs notes. Aucun ordre chronologique n'est déduit des IDs :
la liste est triée par identifiant et seuls les liens `supersedes` indiquent les
remplacements. Pour changer une seule entrée d'un avis groupé, recopier
les choix inchangés des autres entrées dans le remplacement explicite.

`keep` n'applique aucun matériau ; `revise` ne relance aucun calcul GPU ; `discard`
ne supprime aucun candidat. Préparer ensuite une nouvelle demande ou une variante
Blender/Unreal exige toujours le parcours existant et ses vrais inputs, slots et
paramètres. Les notes, même formulées comme des commandes, restent des données.

## Intégrité et conservation

Les enregistrements sont stockés sous
`textures/collection-decisions/review-<review_id>/decision-<decision_id>/` :
`request.json` puis `decision.json`, publié en dernier. Le reçu fixe la demande,
le plan, le hash du reçu de galerie, les IDs/cibles/surfaces et les hashes des
requêtes, candidats, reçus de génération et cartes. Les contrôles détectent les
modifications accidentelles ; ce stockage privé n'est pas une signature externe
ni une preuve d'identité face à un propriétaire pouvant réécrire tous les reçus.

Au plus 128 décisions par revue ; chaque fichier JSON est limité à 256 Kio.
Une entrée incomplète, un fichier supplémentaire, un symlink, un reçu ou un asset
modifié bloque les lectures vérifiées et les nouveaux avis de cette revue.
Inspecter et conserver l'échec localement : pas de reprise automatique, de
réécriture ou de suppression par les outils. Un ID manquant n'est pas recréé.
Conserver les galeries et toute leur provenance, y compris les avis remplacés.

Une galerie partielle conserve ses états capturés : une texture collectée plus
tard nécessite une nouvelle galerie pour recevoir un avis. Les anciennes images
d'entrée ComfyUI ne sont pas requises ; leurs hashes restent une provenance
historique. L'existence d'un avis n'atteste ni sa qualité artistique, ni un rendu
sur mesh, ni l'exécution réelle du modèle GPU ou sa licence.

## CLI Windows

Fermer le MCP propriétaire du workspace. Enregistrer uniquement l'objet `feedback`
de l'exemple dans un fichier UTF-8 `feedback.json` (au plus 128 Kio), puis adapter :

```powershell
$env:PYTHONPATH = (Resolve-Path .\scripts\addons_core).Path
py -3.13 -m cryptonyan_asset_studio.texture_collections `
  --project 'D:\Games\CryptoNyanRunUnreal' `
  --catalog 'D:\CryptoNyanWork\profiles\profiles.json' `
  --workspace 'D:\CryptoNyanJobs\existing-game\textures' `
  decide jade-assets-001 review-001 feedback-001 .\feedback.json
```

Remplacer la dernière ligne par `decisions jade-assets-001 review-001` pour lister,
ou `decision jade-assets-001 review-001 feedback-001` pour lire les notes et hashes.
Le workspace est celui des textures. Aucun besoin de réinstaller ou recréer les
profils ; le catalogue doit rester valide au démarrage du service.

Les tests utilisent des images et assets de test, sans vrai jeu ni GPU. Les essais
dans le vrai Claude/Codex Windows et la validation des matériaux sur copies Blender
et Unreal 5.8 restent dans la [checklist PC](local-pc-checklist.md).
