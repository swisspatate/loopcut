# Diagnostic ComfyUI avant génération — v0.14

`texture_preflight` vérifie un profil configuré avec le **prompt et la seed envisagés**,
en interrogeant les métadonnées de ton ComfyUI local. Il aide à détecter un checkpoint
absent de la liste du chargeur, un nœud indisponible ou un graphe mal raccordé avant
de soumettre une demande de texture pour ton jeu existant.

Le diagnostic fait un seul `GET /object_info` via le client HTTP loopback déjà utilisé.
Il ne crée pas de job, ne modifie aucun fichier du projet, ne télécharge rien et ne
change pas les profils. Il fonctionne sans Blender ni Unreal ouverts. Il faut que
ComfyUI tourne pour obtenir les métadonnées. Sans modèle choisi, le catalogue peut
rester vide ; il faudra configurer un vrai profil avant de le diagnostiquer.

## Utilisation par un agent

Après `texture_profiles`, appeler :

```json
{
  "name": "texture_preflight",
  "arguments": {
    "profile": "texture-base-color",
    "prompt": "Stylized wet stone, uniform lighting, no text",
    "seed": 42
  }
}
```

Remplacer le profil par un identifiant de ton catalogue. Les paramètres sont les
mêmes que ceux du futur `texture_submit` ou `project_texture_submit`, sans identifiant
de job. Le MCP expose désormais **sept outils `texture_*`** avec `--comfy-profiles`
(12 outils avec les missions, 17 avec toutes les interfaces projet).

| Statut | Action à prendre |
| --- | --- |
| `compatible` | Aucun problème dans les vérifications statiques prises en charge. On peut préparer un essai de génération. |
| `blocked` | Corriger le problème indiqué dans le workflow ou l'installation, puis refaire le diagnostic. |
| `needs_review` | Un format dynamique/personnalisé demande une vérification dans ComfyUI. |
| `unavailable` | Vérifier que ComfyUI est démarré, accessible sur le port configuré et retourne des métadonnées valides. |

**Ce diagnostic est explicite et consultatif.** Il n'ajoute pas de prévol automatique
à `texture_submit` et ne change pas sa reprise idempotente. Un agent doit appeler
le diagnostic avant une nouvelle demande, examiner le résultat, puis soumettre si
approprié. Réutiliser un ID de demande existant reste une opération de récupération ;
ne pas créer un nouvel ID pour contourner un résultat incertain.

## Ligne de commande Windows

Depuis le checkout Loopcut, après la [configuration des profils](comfy-agent-profiles.md) :

```powershell
$env:PYTHONPATH = (Resolve-Path .\scripts\addons_core).Path
py -3.13 -m cryptonyan_asset_studio.comfy_preflight `
  'C:\CryptoNyanWork\profiles\profiles.json' `
  --profile texture-base-color `
  --prompt 'Stylized wet stone, uniform lighting, no text' `
  --seed 42
```

Le JSON est écrit sur la sortie standard. Code retour 0 pour `compatible`, 2 pour
les autres statuts ou une configuration locale invalide. Aucun workspace de jobs
n'est nécessaire. Le chargement du catalogue vérifie d'abord le hash approuvé du
workflow ; une modification non approuvée échoue avant tout accès réseau.

## Lire le diagnostic

Chaque problème contient une gravité, un `code`, et si applicable le numéro du
`node` et le nom de l'`input`. Retrouver ce numéro dans l'export API du workflow.

| Code courant | Signification |
| --- | --- |
| `node_unavailable` | La classe du nœud n'est pas exposée par ce serveur ; elle peut être absente ou avoir échoué à se charger. |
| `choice_unavailable` | La valeur configurée n'est pas dans la liste annoncée : checkpoint, LoRA, VAE, sampler ou autre choix. |
| `required_input_missing` | Une entrée obligatoire annoncée manque dans l'export. |
| `literal_type_mismatch` / `literal_out_of_range` | Type ou borne numérique incompatible, y compris pour la seed proposée. |
| `link_node_missing` / `link_output_missing` | Une connexion vise un nœud absent ou un index de sortie invalide. |
| `link_type_mismatch` / `workflow_cycle` | Types de connexion incompatibles ou cycle de dépendances. |
| `channel_not_output_node` | Un canal de texture vise un nœud qui n'est pas déclaré comme sortie. |
| `custom_literal_unchecked` / `dynamic_input_unchecked` | Les métadonnées ne suffisent pas pour une entrée personnalisée/dynamique. |
| `custom_saved_png_output_unchecked` | Un nœud de sortie autre que `SaveImage` nécessite une vérification de ses PNG sauvegardés. |
| `remote_api_node` | Le serveur annonce un nœud d'API externe ; vérifier son fonctionnement et sa configuration dans ComfyUI. |

Le rapport inclut le hash du template approuvé, du graphe effectif après remplacement
du prompt/seed et des métadonnées reçues. Il ne reproduit pas le prompt ni tout le
catalogue de modèles du serveur. Les métadonnées sont relues à chaque appel ; aucun
résultat positif n'est mis en cache. Le modèle ou le serveur peut changer après le
diagnostic : ce rapport n'est pas un verrou de l'installation.

## Portée et limites

- Validation des entrées scalaires standard, choix statiques classiques et `COMBO`,
  bornes min/max, références, indices, types de liens simples et cycles. Tous les
  nœuds de l'export sont examinés, même s'ils ne sont pas reliés à la sortie.
- Les types polymorphes, entrées cachées, schémas personnalisés, `VALIDATE_INPUTS`,
  contraintes de pas, interactions entre paramètres et types étendus ne sont pas
  intégralement interprétés. Des diagnostics conservateurs demandent une revue.
- Une présence dans la liste d'un chargeur **ne vérifie pas les octets du modèle**,
  son chargement, sa licence, sa compatibilité avec les autres modèles ou sa VRAM.
  Les modèles déclarés dans le catalogue ne sont pas attestés par cette API.
- `compatible` ne certifie pas l'exécution GPU, le nombre d'images réellement produit,
  leur format, leur raccordement aux UV ou leur qualité visuelle. Les contrôles PNG
  et Material Doctor restent appliqués lors de la collecte.
- Limites : une réponse de 8 Mio, timeout HTTP de 10 secondes, 256 nœuds, 128 entrées
  par nœud et 100 problèmes affichés avec compte des problèmes omis. Les identifiants
  affichés sont limités à 256 caractères. Les grosses installations peuvent dépasser
  le budget de `/object_info` ; l'interrogation par classe reste une évolution future.
- `submission_performed`, `gpu_execution_validated`, `model_provenance_verified`
  et `distribution_approved` restent `false`.

Référence API inspectée : [serveur ComfyUI](https://github.com/Comfy-Org/ComfyUI/blob/master/server.py),
routes `GET /object_info`, métadonnées `input`, `output`, `output_node`. Les versions
de custom nodes peuvent exposer d'autres schémas ; aucune installation ComfyUI réelle
avec GPU n'a été exécutée dans le cloud.

## Validation sur ton PC

1. Diagnostiquer un profil qui fonctionne déjà dans ComfyUI ; comparer les entrées
   du rapport à celles de l'éditeur et vérifier que la queue ne change pas.
2. Dans une **copie du profil/workflow**, sélectionner un nom de checkpoint inexistant,
   recalculer le hash après examen et vérifier `choice_unavailable`. Ne pas déplacer
   les poids ni modifier le profil de production pour ce test.
3. Tester un nœud absent et un arrêt de ComfyUI : obtenir `blocked` puis `unavailable`.
4. Sur le profil réel, refaire le diagnostic puis une génération explicite et la
   collecte ; contrôler le rendu et la VRAM. Le prévol seul ne valide pas le GPU.

Ces contrôles figurent aussi dans la [checklist centralisée](local-pc-checklist.md#6-comfyui-et-rtx-5080).
