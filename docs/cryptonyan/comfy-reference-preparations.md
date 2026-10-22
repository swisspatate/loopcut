# Choisir une référence ComfyUI depuis l'agent — v0.36

L'agent peut maintenant choisir une image, une carte UV ou un masque pour un
workflow déjà configuré, sans créer un profil par image. Le propriétaire déclare
les emplacements autorisés dans le profil ; l'agent fournit seulement les PNG et
son prompt/seed. Les modèles, connexions et sorties restent ceux du profil approuvé.

## Configuration locale

Partir d'un [profil ComfyUI fonctionnel](comfy-agent-profiles.md) avec un export
**API** dont les connexions consomment déjà les images souhaitées. Après vérification
du graphe et de son hash, ajouter au catalogue `input_root`, le chemin absolu vers
le vrai dossier `input` existant de ComfyUI, sur le même PC. Dans le profil, ajouter
`reference_slots`, par exemple ce **fragment à adapter aux vrais IDs du graphe** :

```json
"reference_slots": [
  {"role": "reference", "binding": ["20", "image"]},
  {"role": "mask", "binding": ["22", "image"]}
]
```

Chaque binding doit désigner un littéral chaîne dans un nœud **LoadImage.image**
existant. Un à trois rôles : `reference`, `uv`, `mask`. Tous les rôles déclarés sont
obligatoires ; ni doublon ni chevauchement avec prompt/seed. Utiliser soit
`reference_slots`, soit les [références fixes](comfy-references.md) `reference_inputs`.
Les profils existants restent valides. Le catalogue est chargé au démarrage : le
revalider avec `python -m cryptonyan_asset_studio.comfy_profiles <catalogue>`, puis
reconnecter le MCP après modification.

Le dossier `input` doit être séparé des sources `--asset-root`, du jeu
`--game-project` et de `<workspace>/textures`, dans les deux sens d'imbrication.
Il peut être un frère de `textures` dans le workspace, ou appartenir à l'installation
ComfyUI. Aucun dossier n'est créé dans le jeu ; aucun upload ni installation implicite.
Les sources se lisent uniquement par handles `asset:` et `work:` sous les racines
déjà configurées, sans symlinks ni chemins absolus. Les chemins des boards ou des
captures doivent d'abord être rendus disponibles dans ces racines par l'opérateur.

## Parcours MCP

Ces exemples supposent un vrai profil nommé `coat-reference`, les deux rôles du
fragment ci-dessus et les vrais fichiers indiqués. Ce ne sont pas des assets ou
workflows fournis avec le dépôt.

1. `texture_profiles {}` : lire les profils, modèles déclarés, sorties et slots.
2. `texture_reference_prepare` : préparer la sélection, sans appel HTTP :

```json
{"profile":"coat-reference","preparation_id":"coat-blue-ref-001",
 "references":{"reference":"asset:references/coat-blue.png",
               "mask":"work:authored/coat-mask.png"}}
```

3. `texture_reference_preflight` : diagnostic live des nœuds/choix, sans calcul :

```json
{"preparation_id":"coat-blue-ref-001","prompt":"Blue stylized cloth","seed":42}
```

4. Pour améliorer un asset existant, préférer `project_texture_reference_submit` :

```json
{"request_id":"coat-blue-001","target":"Content/Characters/Body.uasset",
 "surface":"Coat material slot","preparation_id":"coat-blue-ref-001",
 "prompt":"Blue stylized cloth","seed":42}
```

Sans projet lié, `texture_reference_submit` prend seulement `request_id`,
`preparation_id`, `prompt`, `seed`. Les outils ordinaires `texture_preflight` et
`texture_submit` refusent les profils à slots, pour ne jamais envoyer leur ancien
nom de fichier placeholder. Ils restent disponibles pour les autres profils.

5. Utiliser les outils existants : `texture_status`, puis
`project_texture_collect`, `project_texture_inspect`, `project_texture_image`.
Sans projet, utiliser `texture_collect`, `texture_inspect`, `texture_image`.
La [revue](comfy-texture-review.md) fournit les handles/bindings Studio existants et
la provenance des références : handles d'origine, hashes, dimensions, bindings et
hashes des graphes approuvé/dérivé. Elle ne réaudite pas les anciennes références.

## Reprise et intégrité

La préparation copie les octets exacts en `cn_<sha256>.png` sous `input`. Elle ne
remplace jamais un fichier différent portant le même nom. Trois rôles utilisant
les mêmes octets partagent un fichier. Limites : PNG RGB/RGBA 8 bits non entrelacé,
4096×4096, 32 Mio par image, 64 Mio par sélection ; 256 préparations par workspace.
Il n'y a ni redimensionnement ni fabrication de masque ou de carte supplémentaire.

Les reçus et profils dérivés sont conservés sous
`<workspace>/textures/reference-preparations/<preparation_id>/`. Le choix original
est enregistré avant toute copie ; le reçu final n'est publié qu'après vérification.
Après réponse perdue, réutiliser **les mêmes identifiants et arguments**. Un ID avec
d'autres paramètres est refusé. Une préparation incomplète nécessite une inspection
locale ; le service ne la reprend pas automatiquement. Il peut rester des copies
dans `input`, sans génération. Ne pas les supprimer tant que des calculs les utilisent.

La récupération d'une préparation terminée relit un snapshot vérifié et annonce
`source_freshness_validated=false`. Avant un nouveau prévol ou une nouvelle
soumission, le service revérifie le profil approuvé chargé, les originaux et les
copies dans `input`. Le prévol refait ces contrôles après sa requête de métadonnées.
Une dérive bloque le nouveau travail. Reconnecter après toute modification du catalogue.

Une demande déjà enregistrée ne produit **jamais un second POST**, même si la
réponse a été perdue ou les sources, la préparation ou le profil ont été retirés.
Sa collecte/revue historique utilise les reçus et fichiers conservés ; elle ne
dépend pas de ces anciennes entrées. Les variantes projet recontrôlent en plus le
vrai asset cible. Un état `uncertain` demande une inspection de ComfyUI, pas une
nouvelle demande automatique sous un autre ID.

Les préparations dynamiques servent actuellement des demandes individuelles.
Pour les collections, conserver un profil ordinaire ou les références fixes ; les
profils à slots sont refusés avant création du plan de collection.

## À qualifier sur le PC

Le prévol ne lance pas le GPU et ne prouve pas l'influence sémantique des images.
Les fichiers d'entrée doivent rester inchangés pendant toute l'attente et le calcul :
le contrôle précède l'envoi, pas le chargement exact par les nœuds ComfyUI.
La sortie **MASK** de LoadImage dépend de l'alpha ; un masque RGB blanc/noir exige
une conversion IMAGE-vers-masque déjà raccordée dans le graphe. Aucun guidage UV,
respect des coutures ou accord des slots n'est déduit automatiquement.

Voir la [checklist centrale](local-pc-checklist.md) pour le vrai workflow GPU,
l'affichage dans Claude/Codex sous Windows, le rendu sur une copie Blender et
l'acceptation dans Unreal 5.8. Les tests utilisent du HTTP ComfyUI scripté, pas un
modèle de génération ni les fichiers réels du personnage.
