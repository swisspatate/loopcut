# Checklist des validations sur ton PC

État de référence : CryptoNyan Asset Studio **v0.14**, 21 octobre 2026.
Ce document centralise les vérifications Windows, Blender, Unreal, Claude Code/Codex
et ComfyUI mentionnées dans les guides. Aucune case n'est cochée : nous n'avons pas
encore de résultat de validation de cette extension provenant de ton PC. Les preuves
historiques du projet de jeu sont distinctes. Si tu as déjà effectué une étape,
note son résultat et la version utilisée avant de la cocher.

Les tests cloud comprennent du vrai Blender **Linux 4.3.2** et des tests Python sous
Windows. Ils ne valident pas ton Blender Windows, ton GPU, ton projet Unreal ou tes
connexions aux modèles. Les résultats cloud détaillés restent dans [validation.md](validation.md).

## Ordre conseillé

Pour améliorer le jeu existant, commencer par la section 0. Les kits générés et le
plugin de démonstration sont optionnels ; ne pas remplacer les systèmes déjà en place.

1. Préparer l'environnement et exécuter les tests avec ton Blender.
2. Vérifier les assets, les variantes et les aperçus Blender.
3. Compiler le plugin Unreal, importer les modules et tester le personnage en jeu.
4. Vérifier Claude Code → Codex → Blender avec tes installations réelles.
5. Vérifier ComfyUI et mesurer les performances de la RTX 5080.

Les étapes 4 et 5 sont indépendantes du premier aperçu Blender : elles ne sont pas
nécessaires pour ouvrir un monde créé avec les textures procédurales déjà disponibles.

## 0. Raccorder ton jeu existant (v0.12)

Procédure complète : [passerelle projet](existing-project.md).

- [ ] Pointer `--game-project` vers le checkout Unreal réel ; utiliser un workspace
  externe séparé. Télécharger les fichiers Git LFS nécessaires.
- [ ] Rechercher un asset connu avec `project_inventory` et vérifier son chemin.
  Les classes, dépendances et rigs ne sont pas encore inspectés par cet inventaire.
- [ ] Comparer `project_profiles` au catalogue ComfyUI local. Configurer un workflow
  de texture PNG réellement disponible ; les profils natifs 3D restent distincts.
- [ ] Demander une variante pour un asset de test avec `project_texture_submit`.
  Attendre le succès réel sur GPU et collecter avec `project_texture_collect`.
- [ ] Relancer le service avec le même workspace et le même ID : aucune nouvelle
  soumission ne doit être créée. Vérifier prompt, seed et hash de la source dans les reçus.
- [ ] Sur une copie de test, modifier l'asset après soumission : la collecte liée
  au projet doit signaler une source modifiée. Le résultat générique reste récupérable.
- [ ] Comparer les hashes du projet avant/après : la passerelle ne doit écrire
  ni asset, ni niveau, ni configuration dans le jeu.
- [ ] Examiner les textures dans Blender/Unreal avec les vrais UV, slots, matériaux
  parents et conventions normales. Générer une image ne valide pas sa correspondance
  avec l'atlas de Max ou d'un autre personnage.

La v0.13 implémente l'inspection éditeur et la variante par slot sur copie d'asset.
L'affectation à une sélection d'acteurs en niveau reste à développer.

## 0bis. Inspecteur et variantes Unreal (v0.13)

Guide : [inspecteur et variantes](unreal-material-variants.md). Ces tests nécessitent
le véritable éditeur Unreal 5.8.3 et les assets du jeu ; les tests cloud utilisent des
doubles d'API. Le plugin de démonstration CryptoNyanRuntime n'est pas nécessaire.

- [ ] Sur une copie du projet, inspecter un Static Mesh avec plusieurs slots. Comparer
  classe, noms de slots, chaîne de parents, valeurs effectives et dépendances à l'éditeur.
- [ ] Inspecter le personnage existant : vérifier la référence du Skeleton, sans
  considérer cela comme une validation des poids ou des animations.
- [ ] Créer un candidat ComfyUI pour ce même `.uasset`, puis son `project_material_plan`
  avec des paramètres de textures réellement présents dans l'inspection.
- [ ] Créer la variante dans un nouveau dossier. Vérifier que les textures, l'instance
  et le mesh de revue sont les seuls assets sauvegardés ; comparer les hashes originaux.
- [ ] Vérifier sRGB, compression et relief d'une normale asymétrique : PNG OpenGL,
  une inversion verte à l'import Unreal. Vérifier les erreurs de compilation des shaders.
- [ ] Vérifier que seul le slot choisi change sur la copie et que les réglages hérités,
  autres matériaux, squelette, animations et collisions restent conformes à l'original.
- [ ] Fermer/réouvrir les assets sauvegardés puis refaire la comparaison. Conserver
  le dossier externe `*-inputs` utilisé pour les réimportations de textures.
- [ ] Modifier une source après le plan : vérifier le refus. Tester également une
  source dirty, une destination existante et un paramètre incompatible.
- [ ] Comparer la copie à l'original dans une map de revue et relever coût mémoire,
  shaders et rendu. Aucun succès technique ne vaut approbation artistique.

À développer ensuite : affectation/réversion sur acteurs sélectionnés, captures
avant/après automatisées, couches/VT/ORM et inspection transitive des dépendances.

## 1. Préparer Windows et garder une trace

- [ ] Récupérer la branche `main` du [fork](https://github.com/swisspatate/loopcut)
  dans un checkout complet, avec `scripts/addons_core/loopcut` et
  `scripts/addons_core/cryptonyan_asset_studio`. Ce package se lance en Python ; ce
  n'est pas un ZIP à installer dans les préférences Blender.
- [ ] Repérer le vrai `blender.exe` fourni avec ton installation Loopcut et noter
  sa version exacte. Les guides précédents prennent Blender 5.2.2 comme référence ;
  la version effectivement installée doit figurer dans le compte rendu.
- [ ] Préparer Python 3.13 pour les commandes ci-dessous, ou adapter les commandes
  à une version prise en charge (Python 3.11 minimum).
- [ ] Créer un espace de validation avec des scènes et un projet Unreal de test.
  Les chemins ci-dessous sont des exemples à adapter.

Dans PowerShell, depuis le checkout :

```powershell
Set-Location 'C:\src\loopcut'
$env:PYTHONPATH = (Resolve-Path .\scripts\addons_core).Path
$env:LOOPCUT_BLENDER = 'C:\Tools\Loopcut\blender.exe'
if (-not (Test-Path $env:LOOPCUT_BLENDER -PathType Leaf)) {
    throw 'Corriger le chemin de blender.exe avant de continuer.'
}
$localValidationRoot = Join-Path $env:LOCALAPPDATA 'CryptoNyanValidation'
New-Item -ItemType Directory -Force $localValidationRoot | Out-Null
git rev-parse HEAD
py -3.13 --version
& $env:LOOPCUT_BLENDER --version
py -3.13 -m unittest discover -s loopcut/tests -p 'test_cryptonyan*.py' -v 2>&1 |
    Tee-Object -FilePath "$localValidationRoot\cryptonyan-tests.log"
if ($LASTEXITCODE -ne 0) { throw 'La suite CryptoNyan a échoué : conserver le journal.' }
```

- [ ] Vérifier le succès de la suite **et** l'absence de tests Blender ignorés pour
  cause d'exécutable introuvable. À la v0.14, la suite contient 275 cas, dont 20 tests
  Blender ; les deux tests C++ peuvent être ignorés si `g++` n'est pas disponible. Une version
  ultérieure du dépôt pourra avoir d'autres nombres.
- [ ] Exécuter également `py -3.13 -m unittest discover -s loopcut/tests` depuis
  le checkout complet, avec la configuration de test habituelle du dépôt. Conserver
  le journal et les éventuels tests ignorés ; ne pas confondre cette suite avec celle
  limitée à CryptoNyan. Voir [les instructions de validation](validation.md).
- [ ] Noter versions Windows, Loopcut/Blender, Python, pilote NVIDIA, Unreal,
  Codex CLI et ComfyUI, ainsi que le commit Git testé.

## 2. Missions Blender, Asset Doctor et protection des sources

Procédure : [installation et missions](README.md#windows-installation-and-headless-use).

- [ ] Lancer une mission sur une scène enregistrée et autonome, puis comparer le
  hash SHA-256 du fichier source avant/après. Attendu : source inchangée et rapport
  décrivant les objets réellement analysés.
- [ ] Tester une réparation sur copie : ouvrir la scène retournée et vérifier que
  les objets originaux sont conservés. Les copies corrigées ne remplacent pas les sources.
- [ ] Essayer des assets représentatifs : rig de chat, animations/drivers, parents,
  contraintes, modificateurs, shape keys, données liées, échelles négatives et grandes UV.
  Attendu : opérations non prises en charge clairement refusées ou protégées, sans
  appliquer une réparation destructrice aux rigs.
- [ ] Vérifier chemins longs/Unicode, verrouillage des fichiers et refus de deux
  services utilisant simultanément le même workspace.
- [ ] Tester annulation en file d'attente, annulation pendant un travail Blender,
  expiration du délai et redémarrage du service. Vérifier les statuts, les résultats
  partiels et l'absence de processus enfant restant après une annulation normale.
  La récupération garantie après crash reste un développement distinct (§ 8).

## 3. Export GLB, kits, variantes et aperçus Blender

- [ ] Suivre [Asset Publisher](publisher.md#required-acceptance-on-the-local-installation)
  avec la fixture asymétrique `Platform` ; les cibles `Negative` et `Procedural`
  doivent être refusées. Vérifier géométrie, axes, unités, pivot et matériau après export/réimport.
- [ ] Générer et ouvrir les [kits de runner](runner-kit.md) : `modules.blend` et
  `preview.blend`, dimensions, UV, entrée/sortie et positions des plateformes.
- [ ] Générer les [branches à plusieurs hauteurs et plateformes mobiles](worlds-and-themes.md),
  examiner images entières et sous-images, limites des cycles, puis enregistrer/réouvrir.
- [ ] Produire plusieurs variantes asset × thème avec `theme_batch` et vérifier
  l'affectation correcte des matériaux, les publications et les hashes des sources.
- [ ] Ouvrir [l'aperçu du monde assemblé](world-preview.md), inspecter jonctions,
  biomes, décorations, meshes partagés et animation jusqu'à la fin de la fenêtre commune.
  Examiner les avertissements géométriques ; un contrôle statique réussi ne prouve
  pas la jouabilité ni l'absence de collision pendant le mouvement.
- [ ] Produire [l'aperçu PBR](world-pbr.md) avec `--materials`, puis inspecter en
  **Material Preview** les variantes par biome/module, normales, rugosité et métal.
  Vérifier coutures UV, étirement des textures sur les décorations et densité de texels.
- [ ] Copier uniquement le `.blend` PBR dans un dossier sans textures externes et
  l'ouvrir. Attendu : images embarquées disponibles. Garder séparément le dossier
  complet pour `world_preview check`, puis utiliser `--source` pour contrôler aussi
  les kits et textures d'origine. Vérifier le refus d'un fichier altéré et d'une
  destination existante.

## 4. Unreal Engine 5.8 : import, compilation et jeu

Prérequis : projet C++ de test, toolchain Visual Studio compatible avec la version
UE installée, Python Editor Script Plugin, Editor Scripting Utilities et importeur
glTF/Interchange. Procédure complète : [world-runtime.md](world-runtime.md).

- [ ] Exécuter le `probe(unreal)` du [guide Publisher](publisher.md) et vérifier
  les API réellement disponibles. Une sonde réussie ne suffit pas à valider l'importeur.
- [ ] Importer la fixture asymétrique dans un nouveau dossier de review : contrôler
  quatre triangles, bounds, conversion `(X, -Y, Z) × 100`, pivot, couleur,
  métal/rugosité et persistance après réouverture du projet.
- [ ] Vérifier le refus d'un import déjà présent, d'un GLB altéré et d'un reçu
  existant. En cas d'échec partiel, inspecter le reçu et les assets créés avant de réessayer.
- [ ] Copier `integrations/unreal/CryptoNyanRuntime` dans `Plugins` du projet de test,
  puis **compiler réellement le plugin avec UHT/UnrealBuildTool**. Le test C++ cloud
  ne compile que la formule de mouvement, pas le plugin Unreal.
- [ ] Importer les modules, créer une Empty Level de review et exécuter le placement
  décrit dans le guide. Le plugin de mouvement existe déjà : cette étape consiste
  à le compiler et le valider, pas à le réimplémenter.
- [ ] Contrôler matériaux de palette, échelles, positions initiales, jonctions et
  dégagement des décorations. Le placement laisse le niveau non enregistré : le
  sauvegarder explicitement après inspection, puis le réouvrir.
- [ ] En Play In Editor, exécuter `sample_runtime(plan)` à plusieurs instants et
  vérifier les acteurs manquants/dupliqués et la tolérance de position de 2 cm.
  Ce sont des échantillons de pose, pas un test automatique de jouabilité.
- [ ] Avec le vrai personnage CryptoNyanRun : mesurer vitesse, vitesse de saut,
  gravité effective, rayon de capsule, délai de changement de voie et récupération.
  Reporter ces valeurs dans les recettes et essayer les limites des fenêtres de saut,
  y compris des seeds acceptées et rejetées par le modèle.
- [ ] Marcher entre zones, tester branches hautes/basses, monter sur une plateforme
  mobile et sauter dessus/depuis celle-ci. Vérifier attachement à la base, vitesse
  héritée, rebords, plafonds, obstacles, pause/reprise et reset à **30, 60 et 120 fps**,
  jusqu'aux réglages de mouvement prévus pour le jeu.
- [ ] Vérifier capsule et traces Pawn/Visibility : les plateformes doivent bloquer,
  les décorations non. Le composant fourni utilise une boîte pour nos cuboïdes, en
  query-only ; il ne valide ni physique générale ni canaux personnalisés du projet.
- [ ] Pour les GLB PBR, effectuer une **revue manuelle** dans un nouveau dossier UE :
  connexions du matériau, sRGB, roughness en G/metallic en B, normales OpenGL et conversion
  Unreal, compression, dimensions et rendu. L'import PBR automatique reste bloqué (§ 8).

## 5. Claude Code → Codex → Blender

Procédures : [configuration MCP](README.md#explicit-local-mcp-configuration) et
[adaptateur Codex](codex-adapter.md#local-windows-procedure).

- [ ] Connecter le vrai client Claude Code au serveur stdio, d'abord en mode mock,
  puis avec Blender. Tester les cinq outils : soumettre, consulter, récupérer les
  résultats, annuler et réviser une mission ; vérifier la négociation MCP.
- [ ] Avec l'installation et la connexion Codex habituelles, lancer `probe-codex`.
  Attendu : handshake et compte reconnus. Cela ne prouve pas encore un accès au modèle.
- [ ] Exécuter une petite mission avec `--executor codex`, puis la même chaîne depuis
  Claude Code. Cette étape utilise réellement le compte Codex. Vérifier que les résultats
  proviennent de Blender et de ses rapports, avec le reçu `codex-dispatch.json`.
- [ ] Tester annulation quand Codex attend le réseau et quand Blender travaille,
  puis consultation, révision et redémarrage du service. Vérifier les limites de mission
  et le refus des outils/chemins non autorisés.

L'adaptateur est une délégation Asset Doctor/Publisher bornée. L'orchestration native
générale de plusieurs spécialistes Loopcut n'est pas validée ni achevée par ces étapes.

## 6. ComfyUI et RTX 5080

Procédure et commandes : [material-pipeline.md](material-pipeline.md).
Pour les demandes directes des agents : [profils MCP ComfyUI](comfy-agent-profiles.md).

- [ ] Lancer l'installation ComfyUI locale sur `127.0.0.1:8188`, exporter le workflow
  au **format API**, vérifier les custom nodes, modèles et sorties, puis configurer
  le hash exact du workflow et les vrais champs de seed.
- [ ] Noter les versions/hashes des modèles et leurs licences/attributions. Les reçus
  contiennent des déclarations utilisateur, pas une attestation du serveur sur les poids utilisés.
- [ ] Tester `submit`, `status`, `wait` et `collect` : prompt ID accepté, bons modèles,
  seed, historique, PNG récupérés, hashes et refus d'écraser une sortie existante.
- [ ] Tester suppression d'une tâche **en attente**, course entre attente et exécution,
  timeout, réponse de soumission perdue et historique absent. Inspecter un reçu `uncertain`
  avant de resoumettre. Un timeout de `wait` n'arrête pas le calcul ; l'annulation d'une
  tâche déjà en cours se fait dans ComfyUI, pas par une interruption globale de l'adaptateur.
- [ ] Générer de vraies cartes, attribuer explicitement les canaux avec Material Doctor,
  produire une copie Blender et une publication PBR, puis les utiliser dans les variantes
  et l'aperçu du monde. Contrôler dimensions, normales, coutures et sens physique des canaux.
- [ ] Mesurer temps de génération, pic VRAM/RAM, stabilité et éventuels manques de mémoire
  sur la RTX 5080 avec les résolutions/workflows réellement visés.
- [ ] Configurer au moins un profil réel : workflow API, checkpoint installé, hash
  approuvé, bindings de prompt/seed et sorties. L'exemple livré est un gabarit avec
  placeholders ; aucun modèle n'a été choisi ni installé automatiquement.
- [ ] Valider le catalogue hors ligne, lancer le MCP avec `--comfy-profiles`, puis
  vérifier que l'agent voit les sept outils `texture_*` et les bons profils.
- [ ] Exécuter `texture_preflight` avec le prompt et la seed envisagés, puis vérifier
  que la queue et les fichiers du projet sont inchangés. Comparer les entrées à
  celles de ComfyUI. Procédure : [diagnostic v0.14](comfy-preflight.md).
- [ ] Dans une copie du profil, tester checkpoint et nœud absents, puis ComfyUI
  arrêté : diagnostic `blocked` ou `unavailable`. Les entrées personnalisées peuvent
  demander une revue. `compatible` ne certifie ni le chargement du modèle ni le GPU.
- [ ] Depuis Claude Code ou le client Codex connecté au MCP, demander une texture,
  observer `texture_status`, récupérer le matériau avec `texture_collect` et le
  réutiliser dans une copie Blender. Contrôler visuellement le résultat réel.
- [ ] Redémarrer le MCP après soumission, retrouver la demande avec `texture_jobs`,
  répéter le même ID/paramètres et vérifier qu'aucun deuxième calcul n'est lancé.
  Tester aussi la réponse perdue, les canaux absents et une collecte répétée hors ligne.
- [ ] Vérifier que le même ID avec une autre seed échoue, qu'une modification non
  approuvée du workflow bloque le chargement et que l'agent ne peut pas remplacer
  directement les modèles, nœuds ou chemins de sortie via les arguments MCP.

## 6 bis. Atelier créatif : bâtiments, chat, effets et pouvoirs

Commandes et limites : [creative-toolkit.md](creative-toolkit.md).

- [ ] Construire le kit avec le Blender Windows réel, puis vérifier `creative_kit check`.
  Essayer au moins deux biomes et un matériau récupéré depuis ComfyUI.
- [ ] Ouvrir `architecture.blend` et `environment.blend` : UV/échelle, matériau,
  instances, reliefs, liquide animé, effets, cristaux, éclairage et météo. Vérifier
  les escaliers/paliers/portes et hauteurs libres ; aucun trajet jouable n'est certifié.
- [ ] Ouvrir `cat.blend`, déplacer les quatre contrôles IK et les pôles, lire les six
  clips, regarder les genoux, oreilles, queue, silhouettes, transitions et glissements
  de pattes. Le mesh est un prototype pondéré par segment, pas notre chat final.
- [ ] Importer `cat.glb` dans un dossier Unreal neuf : un skin, six clips, unités/axes,
  root immobile, déformations et matériaux. Documenter les limites de l'importeur
  glTF installé ; ne pas utiliser l'importeur de publication statique sur ce squelette.
- [ ] Compiler le plugin complet v0.2 avec **UnrealBuildTool et UHT** dans UE 5.8,
  avec UMG/Slate/Niagara. Les tests C++ cloud ne compilent que les règles sans moteur.
- [ ] Exécuter la préparation `unreal_creative` dans une carte de review vide.
  Vérifier les cinq cibles, le sol, PlayerStart, matériau Tint, neige, reçu et refus
  de réutiliser une carte/destination occupée. Contrôler puis sauvegarder la carte.
- [ ] Ajouter PowerComponent au personnage, attribuer le matériau et ouvrir le menu
  UMG. Tester les six éléments et quatre formes, énergie/cooldown, fermeture du menu,
  collisions de projectiles et activation aux framerates 30/60/120.
- [ ] Vérifier eau → glace → feu, séchage puis combustion, électricité sur surface
  humide, montée terre et poussée vent. Tester `ResetElements`, un Pawn occupant la
  glace, les obstacles au sweep, le bord de la zone et la limite de 64 cibles.
- [ ] Tester un NiagaraSystem local avec `User.Color`, sa destruction après 3 s,
  l'import des atlas SubUV 4×4, le changement météo et leur coût GPU/CPU/VRAM.
- [ ] Sauvegarder/réouvrir la carte et vérifier les réglages d'atmosphère ; contrôler
  l'éclairage/exposition et les particules sous des toits. La météo n'est pas occultée
  automatiquement par l'architecture et les liquides ne simulent pas la physique.
- [ ] Vérifier que le mode réseau est refusé ; aucune compatibilité multijoueur
  n'est déclarée. Consigner séparément tout problème de compilation ou d'API moteur.

## 7. Preuves à conserver pour chaque validation

Noter le statut **à faire / réussi / échec / bloqué**, plutôt que cocher une étape
qui n'a pas pu être exécutée. Le succès d'une suite avec des tests ignorés ne les valide pas.

| Élément | À renseigner |
| --- | --- |
| Étape, date, personne | Numéro de section et vérification effectuée |
| Environnement | Commit Git, versions des logiciels, GPU et pilote |
| Entrée | Recette, seed, objets ciblés et hashes des sources |
| Exécution | Commande exacte, durée, code de sortie et tests ignorés |
| Résultat | Journal, reçu JSON, capture ou vidéo si utile, hashes après exécution |
| Échec/blocage | Message complet, résultat attendu et marche à suivre pour reproduire |

Pour les performances et comparaisons visuelles, conserver aussi caméra, frame,
éclairage, gestion des couleurs, résolution et paramètres de rendu identiques.
La qualité artistique reste une appréciation humaine ; aucun score automatique
ou benchmark GPU réel n'a été établi dans le cloud.

## 8. Encore du développement, pas seulement une validation sur ton PC

Ces limites ne se résolvent pas en cochant les étapes précédentes :

- **Import PBR Unreal automatique** : validation des textures et des graphes de
  matériaux à implémenter avant d'autoriser `apply` sur les packages texturés.
- **Intégration native Claude/Codex/multi-spécialistes Loopcut** : intégration des
  rôles, ownership/review/merge et supervision durable à poursuivre ; `CODEX_SPEC`
  et `ORCH_SPEC` restent deux modes distincts.
- **Supervision Windows après crash** : Windows Job Objects et récupération fiable
  des processus à développer ; les tests d'annulation normale ne garantissent pas ce cas.
- **PCGEx natif** : plugin compatible à choisir/figer et mapping des points à vérifier
  localement si cette voie est retenue ; adaptateur versionné et graphes natifs non fournis.
  Le CSV est une table neutre. Le placement de review via notre plugin constitue une autre voie.
- **Rig du chat définitif, skin organique, retargeting/Control Rig et root motion** :
  restent à développer ; le rig quadrupède généré et ses six clips existent depuis v0.11.
- **Navigation architecturale certifiée, fluides physiques, grottes, génération de
  graphes Niagara, inventaire/carte/progression, LOD/collisions pour assets arbitraires,
  portails traversables, objectifs, plateformes de phase, echo-cat et multijoueur** :
  futurs développements. Les pouvoirs solo, surfaces réactives, météo, menu de test,
  cuboïdes et lifts disposent maintenant de code runtime à valider localement.
- **Vidéo ComfyUI et autres outils externes** : l'adaptateur actuel collecte des PNG,
  pas des vidéos ; les intégrations listées dans la roadmap ne sont pas toutes installées.
- **Régressions visuelles automatisées et banc de performances** : automatisation à
  développer ; les captures et mesures locales ci-dessus fourniront les références.

Voir [roadmap.md](roadmap.md) pour les développements et les guides liés ci-dessus
pour les commandes détaillées. Lors d'une nouvelle fonctionnalité ou d'un test sur
ton PC, mettre cette checklist et les preuves correspondantes à jour.
