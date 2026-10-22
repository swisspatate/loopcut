# Checklist des validations sur ton PC

## v0.38 — Galerie locale des textures collectées

Guide : [collection-review.md](collection-review.md).

- [ ] Mettre à jour main et reconnecter le MCP ; vérifier project_collection_review et project_collection_review_artifact avec les services textures/projet. Les anciens profils et plans restent compatibles.
- [ ] Sur un vrai lot partiel puis terminé, créer deux revues avec des IDs différents. Confirmer que les cartes et références correspondent aux bons assets/surfaces, qu'une entrée non collectée reste indiquée comme telle et qu'aucun calcul ou téléchargement ComfyUI n'est déclenché.
- [ ] Ouvrir gallery_file dans le navigateur Windows local. Examiner l'affichage des quatre canaux disponibles, dimensions, couleurs, accents et dispositions sur différentes largeurs. La page doit fonctionner sans réseau ni JavaScript.
- [ ] Dans le vrai Claude/Codex Windows, lire un artefact listé et afficher une carte PNG jusqu'à 2 Mio. Une copie locale entre 2 et 8 Mio peut s'afficher dans le HTML sans contourner la limite MCP. Les cartes omises restent à examiner dans leurs résultats d'origine.
- [ ] Après progression du lot, rappeler le même review_id : il doit conserver l'ancien instantané. Utiliser un nouvel ID pour la nouvelle revue. Sur une copie de validation, modifier un asset cible puis confirmer le refus des lectures vérifiées. L'ouverture directe de l'ancien HTML n'effectue pas ce contrôle.
- [ ] Conserver plans, reçus et candidats pour vérifier les revues. Contrôler les images de référence comme provenance historique ; leur affichage textuel ne certifie pas leur fraîcheur ni leur influence dans le vrai workflow GPU.
- [ ] Réutiliser les request_id d'origine avec project_texture_inspect pour les handles de matériau, puis examiner le rendu sur les copies Blender Windows et Unreal 5.8. Vérifier les UV, vrais slots et paramètres avant toute adoption ; la galerie n'applique aucun matériau.

## v0.37 — Références différentes par entrée d'un lot ComfyUI

Guide : [texture-collections.md](texture-collections.md).

- [ ] Mettre à jour main puis reconnecter le MCP. Vérifier que project_collection_plan expose preparation_id dans ses entrées ; les anciens profils, plans et outils restent valides.
- [ ] Avec un vrai workflow API à reference_slots, préparer deux sélections par texture_reference_prepare depuis les racines autorisées, puis créer un lot de deux copies d'assets avec ces vrais IDs. Confirmer que le plan ne lance aucun calcul et fixe les bons hashes, cibles, prompts et seeds.
- [ ] Avancer/collecter une entrée à la fois. Dans ComfyUI GPU, confirmer que chacune consomme son propre PNG préparé, que le modèle/LoRA et les connexions restent ceux du profil, et que les masques utilisent l'alpha ou la conversion prévue. Ne pas modifier input pendant la queue ou le calcul.
- [ ] Depuis le vrai Claude/Codex Windows, demander ce parcours sans citer les outils et examiner ses appels. Après collecte, vérifier chaque candidat via project_texture_inspect/project_texture_image : référence d'origine, hashes, rendu affiché et source cible inchangée.
- [ ] Sur des copies de validation, modifier une référence avant son envoi : l'entrée concernée doit être bloquée. Une entrée déjà envoyée doit rester récupérable avec le même request_id ; aucun nouvel ID ni préparation de remplacement automatique ne doit être créé après une réponse perdue.
- [ ] Vérifier l'index terminé : ID/empreinte de préparation et candidat corrects pour chaque entrée. Sa relecture est historique et ne certifie pas l'état actuel des anciennes références. Garder plans, reçus et candidats ; les assets cibles restent recontrôlés.
- [ ] Si le parcours CLI est utilisé, fermer le MCP propriétaire puis fournir --studio-workspace et --asset-root correspondant à sa configuration pour planifier/avancer un nouveau lot guidé.
- [ ] Examiner palette, motifs, coutures, UV et vrais slots sur les copies Blender Windows et Unreal 5.8 avant adoption. Un style commun ne garantit pas la cohérence artistique ; les tests HTTP scriptés ne qualifient pas le GPU ni les vrais assets du jeu.

## v0.36 — Références ComfyUI choisies par l'agent

Guide : [comfy-reference-preparations.md](comfy-reference-preparations.md).

- [ ] Mettre à jour main et reconnecter le MCP. Vérifier texture_reference_prepare/preflight/submit et project_texture_reference_submit quand les services sont configurés. Les anciens profils restent utilisables ; aucune réinstallation de modèles.
- [ ] Dans un vrai export API testé, déclarer les bons LoadImage.image via reference_slots et le vrai dossier input_root de ComfyUI. Garder ce dossier séparé des assets, du jeu et de textures. Revalider le catalogue puis reconnecter.
- [ ] Placer une référence et un masque/UV réels sous asset-root ou workspace ; demander à l'agent de les préparer, lancer le prévol et générer une petite texture avec le profil configuré. Vérifier ses vrais appels/arguments, les fichiers cn_<sha256>.png et les reçus ; aucune connexion de graphe ni nom de modèle ne doit être inventé.
- [ ] Vérifier dans ComfyUI GPU l'influence des références. Pour MASK, confirmer l'alpha ou la conversion explicite IMAGE-vers-masque. Contrôler résolution, coutures UV et fidélité au personnage ; les tests de protocole ne valident pas ce résultat artistique.
- [ ] Conserver les PNG préparés tant que la queue/calcul les utilise. Après réponse perdue, reprendre les mêmes IDs ; une demande uncertain ou une préparation incomplète exige une inspection locale, sans nouveau calcul automatique.
- [ ] Générer un candidat lié au vrai asset avec project_texture_reference_submit, puis collecter/inspecter/afficher dans le vrai Claude/Codex Windows. Vérifier les empreintes et provenance ; une modification contrôlée de copie source doit bloquer une nouvelle soumission ou revue liée.
- [ ] Examiner le matériau sur une copie dans Blender Windows puis Unreal 5.8 avec les vrais slots/paramètres. Cette version n'applique rien au jeu. Les collections restent à références fixes ; les sélections dynamiques sont individuelles.

Les tests CPU/HTTP scripté ne constituent pas une génération GPU ni une validation
des clients IA, du vrai rig, de Blender Windows ou d'Unreal.

## v0.35 — Revue des textures ComfyUI depuis l'agent

Guide : [comfy-texture-review.md](comfy-texture-review.md).

- [ ] Mettre à jour le clone et reconnecter le MCP. Avec des profils ComfyUI configurés, vérifier texture_inspect/texture_image ; avec le projet configuré, vérifier aussi project_texture_inspect/project_texture_image. Les profils existants restent compatibles.
- [ ] Avec un vrai workflow API et ses modèles/nœuds installés, demander une petite texture : profils → preflight → soumission → suivi → collecte → inspection → image. Vérifier que l'agent utilise un profil réel et conserve le même identifiant après perte de réponse.
- [ ] Confirmer dans Claude/Codex Windows l'affichage natif des cartes déclarées, leurs dimensions et espaces couleur. Les PNG de plus de 2 Mio restent à examiner localement ; aucun redimensionnement ni canal supplémentaire n'est fabriqué.
- [ ] Pour un vrai asset existant, utiliser les variantes project_texture_* ; après modification contrôlée d'une copie source, confirmer le refus de la revue liée. Une revue générique peut lire l'ancien snapshot, sans le présenter comme actuel.
- [ ] Réutiliser les handles/bindings fournis pour les couches PBR Studio, avec un masque réel sous le même dossier de sources autorisé. Respecter les limites existantes (un mégapixel, mêmes dimensions, alpha opaque, cartes scalaires grises et normales OpenGL). Examiner le résultat sur une copie du vrai asset.
- [ ] Qualifier les UV, coutures, slots et paramètres du vrai matériau dans Blender Windows puis Unreal 5.8. La revue ne modifie ni n'adopte les matériaux du jeu et ne prouve pas une licence ou une qualité artistique.

Les tests cloud utilisent un protocole ComfyUI scripté et de véritables fichiers
PNG/PBR composés sur CPU, sans inférence GPU. Les vrais modèles, clients IA,
Blender Windows et Unreal restent des validations locales distinctes.

## v0.34 — Mise à jour et réutilisation de snapshots

Guides : [mise à jour Windows](updating-windows.md), [inspection et reprise explicite](workflow-reuse.md).

- [ ] Fermer les connexions et Blender après arrêt confirmé du travail ; mettre à jour le clone propre sur main avec git pull --ff-only origin main, puis reconnecter le MCP. Les profils existants restent compatibles ; conserver les chemins des lanceurs, le dossier de travail et les sources.
- [ ] Vérifier studio_workflow_inspect, studio_workflow_step_artifact et studio_workflow_fork dans Claude/Codex. Le diagnostic --probe-mcp ne prouve pas les choix du modèle : demander depuis un prompt ordinaire de corriger une étape échouée en réutilisant le préfixe réussi, puis examiner ses appels et paramètres réels.
- [ ] Sur une copie du personnage, terminer un audit Blender puis provoquer un échec de plan contrôlé. Lire le rapport conservé, corriger la politique explicite, créer un fork et vérifier sous Windows que l'audit n'est pas recalculé, que le candidat est sauvegardé/rouvert et que la source est préservée.
- [ ] Faire une composition avec de vraies cartes ComfyUI conservées : vérifier hashes, masque, pixels et rendu sur le vrai asset. La réutilisation concerne les cartes capturées ; aucune nouvelle génération GPU n'est implicite.
- [ ] Après modification d'un fichier source du jeu, demander une analyse fraîche : vérifier que l'agent relance les étapes concernées au lieu de présenter un snapshot comme réaudit actuel. Conserver tous les anciens dossiers référencés ; leur suppression doit invalider la lecture du nouveau résultat.
- [ ] Confirmer qu'un critère rejeté reste lisible mais non réutilisable, qu'un parcours actif/interrompu est exclu, et qu'un nouveau parcours utilise un nouvel identifiant. Après perte de réponse, retrouver le même identifiant sans nouveau calcul.
- [ ] Préparer un nouveau handoff Unreal : son script doit viser le nouveau dossier de résultats. Relire puis exécuter explicitement dans le bon Unreal 5.8 ; seule cette étape locale qualifie l'éditeur.

Les preuves cloud incluent une composition PBR réelle après retrait des sources,
un audit Blender 4.3.2 réutilisé pour une copie de rig vérifiée et un client stdio.
La CI portable vérifie Python sur Windows ; le vrai Blender Windows, les applications
Claude/Codex, Unreal et ComfyUI GPU restent à qualifier sur le PC.

## v0.33 — Parcours avec plusieurs étapes

Guide : [studio-workflows.md](studio-workflows.md).

- [ ] Mettre à jour le dépôt Windows et reconnecter Claude Code/Codex ; vérifier la capacité workflow_automation, studio_workflow_template et l'opération workflow_run. Les profils existants restent compatibles.
- [ ] Depuis un prompt ordinaire, demander de préparer puis prévisualiser un parcours caméra ou un niveau modulaire. Vérifier les paramètres réels choisis par l'agent, les prérequis affichés et le suivi d'un seul identifiant avec états par étape.
- [ ] Composer un vrai matériau à partir de cartes déjà collectées depuis ComfyUI avec le modèle material_layers. Examiner les UV, le masque et le rendu sur une copie du vrai asset ; cette version n'enchaîne pas les appels réseau ComfyUI.
- [ ] Sur une copie du rig existant, fournir une politique de réparation explicite au modèle rig_repair_copy ; vérifier le candidat sauvegardé/rouvert et la conservation du fichier source, puis examiner les déformations avant adoption.
- [ ] Ajouter un critère adapté au vrai rapport ; provoquer un rejet contrôlé et confirmer que les étapes suivantes restent bloquées. Un succès technique d'audit peut encore contenir des défauts si aucun critère n'a été configuré.
- [ ] Annuler un parcours Blender pendant une étape ; attendre cancelled et vérifier l'arrêt du processus sous Windows ainsi que l'absence de démarrage de l'étape suivante.
- [ ] Après reconnexion ou réponse perdue, retrouver le même identifiant sans double calcul. Sur un essai d'arrêt brutal, vérifier interrupted et les étapes bloquées, examiner les sorties/processus restants et ne relancer que volontairement sous un nouvel identifiant.
- [ ] Pour un parcours comparison_plan → unreal_handoff, relire le script puis l'exécuter dans le bon projet Unreal 5.8 ; sa génération seule ne valide pas l'éditeur, le rendu ou le gameplay.

Les preuves cloud comprennent de vraies chaînes PBR, caméra Blender Linux, modules
GLB, candidat de réparation de rig sauvegardé/rouvert et recette Image Workshop
rendue/exportée. Les clients IA réels,
Blender Windows, Unreal 5.8 et ComfyUI GPU restent des validations locales distinctes.

## v0.32 — Opérations longues et annulation

Guide : [background-operations.md](background-operations.md).

- [ ] Mettre à jour le dépôt Windows et reconnecter les deux clients ; vérifier `studio_submit`, `studio_cancel` et `studio_jobs` en plus des outils existants. Les profils restent compatibles.
- [ ] Demander un vrai traitement long depuis un prompt ordinaire. Vérifier que l'agent utilise la soumission asynchrone, suit le même identifiant et espace ses lectures ; la réponse initiale `queued` n'est pas un résultat terminé.
- [ ] Sur une copie d'asset, lancer une opération Blender, en mettre une seconde en attente, annuler la seconde puis la première. Attendre `cancelled` et confirmer dans le Gestionnaire des tâches que Blender et ses enfants sont arrêtés. L'arrêt d'un vrai Blender Windows reste à qualifier.
- [ ] Vérifier que les rapports terminés restent lisibles, que les sorties partielles annulées ne sont pas présentées comme validées et qu'un identifiant renvoyé après perte de réponse ne déclenche pas un deuxième calcul.
- [ ] Fermer normalement le MCP pendant une opération de revue : confirmer l'annulation avant libération du workspace. Après une fermeture brutale sur un essai contrôlé, vérifier `interrupted`, l'absence de reprise et les éventuels processus Blender restants avant de relancer avec un nouvel identifiant.
- [ ] Retrouver l'historique avec `studio_jobs {"limit": 20}` après reconnexion. Garder un seul traitement GPU lourd à la fois entre Claude, Codex et ComfyUI : la file Studio n'est pas un arbitre GPU global.

Les tests cloud Linux couvrent un vrai aperçu caméra et un vrai processus Blender
annulé après sauvegarde d'une copie partielle. La CI portable couvre les processus
Python/enfants Windows ; elle ne valide ni Blender Windows ni les vrais clients
Claude/Codex. Unreal 5.8 et la génération ComfyUI restent des essais locaux distincts.

## v0.31 — Découverte et choix des outils par l'agent

Guide : [agent-routing.md](agent-routing.md).

- [ ] Mettre à jour le dépôt Windows et redémarrer/reconnecter le MCP dans Claude Code et Codex ; vérifier studio_catalog/route/guide/execute/operation/artifact et le prompt cryptonyan_workflow.
- [ ] Vérifier que chaque client reçoit les consignes ; si nécessaire, exporter guidance dans un nouveau dossier, puis intégrer les règles utiles à ses instructions existantes après lecture.
- [ ] Tester de vrais prompts sans noms d'outils : texture de bâtiment, textures pour plusieurs assets, vêtement traversant le corps, travelling, niveau à checkpoints, comparaison de skins. Observer les choix réels et les arguments du modèle ; le routeur lexical ne garantit pas ces choix.
- [ ] Vérifier que les prérequis absents apparaissent et que l'agent inspecte/demande les noms réels plutôt que d'inventer profils, slots, os, actions ou identifiants de workflows.
- [ ] Exécuter une opération CPU puis un petit worker Blender sur une copie ; vérifier les handles asset:/work:, les reçus et les artefacts lus par MCP sous Windows.
- [ ] Préférer studio_submit depuis v0.32 pour Blender ; si studio_execute est utilisé, adapter le timeout client. Vérifier le même identifiant après une réponse perdue et l’état interrupted après un redémarrage brutal.
- [ ] Avec les vrais profils ComfyUI, vérifier le parcours profiles→preflight→submit/status→collect et les collections multi-assets ; aucune inférence GPU n'est validée par le catalogue.
- [ ] Relire puis lancer un handoff de revue dans le vrai Unreal 5.8 et le bon projet ; contrôler les résultats d'éditeur séparément du reçu MCP qui ne prouve que la création du script.

Les tests cloud couvrent 26 prompts FR/EN, le protocole stdio et un vrai appel MCP
vers Blender Linux. Ils n'appellent aucun modèle Claude/Codex et ne valident pas
les applications clientes, le GPU ComfyUI ou Unreal du PC. TRELLIS conserve ses
prérequis de workflows API et de collecte 3D encore à implémenter.

## v0.30 — Scène de comparaison Unreal commune

Guide et parcours console : [unreal-comparison.md](unreal-comparison.md).

- [ ] Dans Unreal 5.8, créer/enregistrer une carte de revue vide sans actors de template ; sauvegarder les sources, vérifier les vrais chemins/slots et préparer le plan hors du projet.
- [ ] Tester la création de la scène avec StaticMesh puis SkeletalMesh, la conversion mètres→cm, le cadrage, les lumières et le mode d'exposition manuel. Les protocoles cloud utilisent uniquement des doubles d'API Unreal.
- [ ] Piloter la caméra créée et qualifier localement les API Python de caméra/lumières et la visibilité séquentielle. Ajuster l'exposition dans la recette puis reconstruire une session si le rendu est inadapté.
- [ ] Sur le vrai personnage, examiner la pose de référence puis un temps figé d'AnimSequence compatible : os réellement évalués, morphs, post-process d'animation, LOD et différence avec l'Animation Blueprint. La relecture des données ne prouve pas la pose affichée.
- [ ] Vérifier qu'une modification de source, caméra, lumière, transform, slot, acteur ou visibilité bloque sélection et collecte ; conserver les reçus et ne pas enregistrer/changer la carte pendant la session.
- [ ] Après stabilisation des shaders/textures/Lumen/TSR, capturer manuellement chaque variante avec les mêmes dimensions/ratio, collecter les PNG et ouvrir la galerie HTML sous Windows.
- [ ] Comparer visuellement les images et qualifier les conditions de capture ; les PNG fournis ne sont pas authentifiés par le renderer. Aucun benchmark GPU ni adoption d'asset n'est implémenté ici.
- [ ] Fermer la carte sans sauvegarder après revue ; pour un nouvel essai, préparer une carte vide et un nouveau dossier/session.

Les fonctions de capture moteur, mesures GPU, collage de plusieurs vêtements dans
la scène et adoption contrôlée restent au suivi de développement, pas à une case
de validation de fonctions déjà livrées.

## v0.29 — Essayage animé des vêtements existants

Guide et spécification : [animated-wardrobe.md](animated-wardrobe.md).

- [ ] Préparer une copie autonome du vrai personnage, textures intégrées, actions enregistrées et mapping explicite des noms/slots ; utiliser un corps ou proxy fermé, orienté vers l'extérieur.
- [ ] Tester le panneau Blender Windows et la CLI avec des chemins D: contenant des espaces ; garder la destination hors des assets du jeu.
- [ ] Essayer plusieurs vêtements déjà riggés sur course, saut, accroupissement et poses extrêmes ; adapter les fenêtres, la tolérance en mètres et le budget d'influences.
- [ ] Ouvrir review.html, le CSV et chaque copie .blend ; vérifier pire pose, marqueurs, sélection du vêtement, conservation des poids, shape keys et action/slot attendu.
- [ ] Comparer visuellement les alertes et les zones concaves/auto-intersectées du vrai corps : signe de normale et rayons BVH ne certifient pas l'absence de pénétration.
- [ ] Inspecter entre les frames et entre couches de vêtements ; ces collisions ne sont pas couvertes par le diagnostic actuel.
- [ ] Sur une copie de test Unreal 5.8, qualifier le Skeleton, les influences, les normales, LOD, matériaux et éventuel Chaos Cloth avant adoption dans le jeu.

Les tests cloud utilisent de vrais Blender Linux et des assets procéduraux. Ils ne
valident pas l'affichage Windows, les vrais assets ou la simulation Unreal.

## v0.28 — Niveaux modulaires à contraintes

Guide et parcours de démonstration : [modular-levels.md](modular-levels.md).

- [ ] Sur Windows, générer le kit démo avec le vrai exécutable Blender puis composer, vérifier et ouvrir l'aperçu ; tester le panneau et les chemins D: avec espaces.
- [ ] Exporter quelques vrais modules statiques du décor, avec pivots/échelles baked, portes centrées, hashes GLB et proxies de murs fidèles ; vérifier l'absence de textures manquantes dans la copie Blender.
- [ ] Adapter rayon, hauteur et marge à la capsule du personnage ; examiner les dégagements centre→porte, angles, collisions et raccords.
- [ ] Tester des seeds, checkpoints, pièces à thème, branches et boucles ; vérifier qu'aucun détour n'évite les checkpoints déclarés.
- [ ] Mapper les vrais StaticMeshes Unreal, reconstruire le bundle, ouvrir une carte de revue vide enregistrée et exécuter le dry-run de `unreal_modular.review`.
- [ ] Vérifier le refus si le pivot/les bornes d'un mesh ne correspondent pas au GLB ; lancer apply uniquement dans la carte de revue prévue et examiner les reçus.
- [ ] Dans Unreal 5.8, qualifier collisions, NavMesh, sauts/déplacements du vrai personnage et coût GPU avant adoption. Aucune simulation moteur n'a été exécutée dans le cloud.

Les preuves cloud couvrent de vrais GLB et aperçus Blender Linux, ainsi que des
protocoles Unreal testés avec doubles d'API. PCG/HISM natif, terrain et étages restent
au suivi de développement.


## v0.27 — Sélection et masques interactifs

Guides : [scene-selection.md](scene-selection.md), [mask-paint.md](mask-paint.md).
Suivi des six chantiers : [game-improvement-workshop.md](game-improvement-workshop.md).

- [ ] Charger les nouveaux panneaux Blender Windows et exporter la sélection réelle du personnage et de son rig ; contrôler les UV, slots, os, actions et unités signalés.
- [ ] En mode interactif avec GPU, exporter avec le viewport ; vérifier la vue, la frame, le contenu visible, les réglages rétablis et l'image reçue par l'agent. Cette capture graphique n'a pas été exécutée dans le cloud.
- [ ] Reconnecter Claude/Codex au MCP et tester les outils `reference_scene_*` et `reference_mask_*` avec la bibliothèque configurée.
- [ ] Ouvrir l'éditeur HTML hors ligne dans le navigateur Windows ; tester souris/stylet, redimensionnement de fenêtre, pinceau, gomme, annulation/rétablissement et téléchargement/reprise du JSON.
- [ ] Réimporter le tracé dans Blender, comparer le PNG gris à la zone dessinée et vérifier le refus si la référence a changé. L'automatisation Node couvre les événements/raster mais ne remplace pas cet essai graphique.
- [ ] Peindre un masque sur une texture réellement compatible avec les UV, composer une variante PBR et l'examiner sur une copie animée du personnage.
- [ ] Dans le vrai workflow ComfyUI, vérifier la conversion de l'IMAGE grise en MASK, le sens blanc/noir et le résultat d'inpainting avant d'utiliser le profil dérivé.
- [ ] Examiner ensuite le matériau dans la carte de revue Unreal 5.8. Les captures et masques ne modifient pas automatiquement les assets du jeu.


## v0.26 — Couches PBR et mouvements caméra

Guides : [material-layers.md](material-layers.md), [camera-moves.md](camera-moves.md).

- [ ] Dans Blender Windows, tester les deux nouveaux panneaux, les chemins sur D: et leur réactivation après désactivation.
- [ ] Exporter de vrais matériaux Ucupaint ou collecter les résultats ComfyUI ; garder les reçus de génération et constituer des bundles PBR explicites.
- [ ] Composer plusieurs couches avec des masques peints adaptés aux UV du personnage ou du décor ; examiner les coutures, les normales et la distinction des canaux.
- [ ] Qualifier la limite actuelle de 1 Mpx et le temps de calcul synchrone sur le PC ; préparer des cartes de test à résolution réduite si nécessaire.
- [ ] Appliquer le résultat sur une copie de l'asset, puis importer une variante dans Unreal 5.8 avec les outils existants ; contrôler normales +Y, couleur, roughness, metallic et rendu réel.
- [ ] Créer des trajectoires caméra avec des coordonnées du vrai niveau, ouvrir l'aperçu Blender et inspecter les coupes et le mouvement entre les clés.
- [ ] Exécuter le plan Director dans Unreal 5.8 sur une nouvelle séquence de revue ; vérifier repères, visée, interpolation, focale, capteur et absence de traversée du décor.

La CI Windows valide le Python portable ; elle ne qualifie ni l'affichage Blender
Windows, ni Ucupaint installé, ni ComfyUI GPU, ni l'API réelle Unreal 5.8.


## v0.25 — Versions visuelles des candidats

Guide : [visual-versions.md](visual-versions.md).

- [ ] Dans Blender Windows, créer un historique sur D: hors du jeu et déclarer le projet Unreal ; vérifier l'affichage et les chemins avec espaces.
- [ ] Construire deux vrais candidats, les archiver et comparer références, rendus et recettes dans le HTML.
- [ ] Archiver avec une référence du tableau ; vérifier le refus si l'image, la recette ou l'asset lié a changé.
- [ ] Retenir puis restaurer une version dans un nouveau dossier ; ouvrir manuellement le `.blend` copié et vérifier géométrie, textures intégrées et caméra.
- [ ] Tester le refus d'une destination existante, dans l'historique ou dans le projet déclaré ; vérifier qu'une édition CLI impose de recharger le panneau.
- [ ] Sur une copie de test, modifier un fichier archivé et constater le refus de sélection/restauration.
- [ ] Importer le GLB restauré dans une carte de revue Unreal 5.8 et qualifier échelle, matériaux, collisions et coût GPU. Aucun import automatique n'est ajouté ici.


## v0.24 — Tableau de références visuelles

Guide : [reference-boards.md](reference-boards.md).

- [ ] Charger le panneau Blender Windows et créer un tableau hors du projet ; tester une vraie image PNG et ses miniatures.
- [ ] Enregistrer notes et rectangles ; ouvrir la revue HTML et vérifier leur alignement sur des images horizontales et verticales.
- [ ] Tester les chemins D: avec espaces, recharger après redémarrage et vérifier le refus d'une ancienne révision après édition depuis la CLI.
- [ ] Lier un vrai asset téléchargé via LFS ; vérifier `unchanged`, puis le refus de préparation après modification de la source.
- [ ] Ajouter la bibliothèque au profil de connexion et reconnecter Claude/Codex ; vérifier `reference_boards`, `reference_read` et la réception visuelle de `reference_image`.
- [ ] Fournir une recette explicite adaptée à l'image, préparer le bundle, construire un candidat puis comparer les hypothèses, proportions et détails.
- [ ] Sur une sortie TRELLIS réelle, vérifier la provenance et le contrat GLB avant préparation. Le tableau ne lance pas TRELLIS.
- [ ] Examiner le candidat dans une carte de revue Unreal, sans remplacer les sources ; cette version n'applique aucun changement au jeu.

Les rectangles sont saisis numériquement et visibles dans la revue HTML ; le dessin
à la souris et le canevas libre restent à développer ; les versions de candidats sont ajoutées en v0.25.

## v0.23 — Connexions des agents

Guide : [agent-connections.md](agent-connections.md). Suivi : [inspirations Mixar](mixar-integration.md).

- [ ] Renseigner le Python autonome 3.11+, Blender, les assets et un dossier de travail séparé, avec les vrais chemins sur C: ou D:.
- [ ] Dans Blender Windows, enregistrer le panneau, charger/enregistrer le profil et vérifier le presse-papiers JSON Claude/TOML Codex.
- [ ] Vérifier l'affichage, le diagnostic en arrière-plan, le changement de champs pendant le test et la désactivation du panneau pendant un test.
- [ ] Ajouter l'entrée MCP sans supprimer les autres serveurs ; reconnecter Claude Code puis Codex et vérifier les outils réellement visibles.
- [ ] Lancer `check --probe-mcp` avec une file active et vérifier qu'aucune mission de cette file n'est modifiée/reprise par le diagnostic.
- [ ] Tester une petite mission Asset Doctor depuis chaque application ; vérifier les résultats dans `mcp-claude` / `mcp-codex` et l'arrêt normal.
- [ ] Tester ComfyUI arrêté puis lancé ; distinguer `unavailable`, `reachable`, catalogue valide et génération GPU réellement réussie.
- [ ] Si le projet Unreal est configuré, vérifier l'inventaire depuis l'agent puis une petite texture liée à un asset existant.

Ce panneau ne pilote pas la scène Blender ouverte et ne remplace pas la validation
de l'adaptateur Claude → Codex → Blender. Les tableaux de références sont ajoutés
en v0.24. Les couches de matériaux et nouveaux mouvements de caméra inspirés de
Mixar restent dans le suivi de développement.


## v0.22 — Atelier image → candidat 3D

Guide : [image-workshop.md](image-workshop.md). Recherche : [générateurs et licences](image-to-3d-providers.md).

- [ ] Windows : lancer `prepare`, `inspect-glb` et `build` avec le vrai Blender local ; vérifier les chemins contenant des espaces.
- [ ] Donner une vraie référence à l'agent, préciser une dimension et examiner sa recette/hypothèses avant d'adopter le résultat.
- [ ] Ouvrir `comparison.html` et le `.blend` : silhouette, proportions, faces cachées, cadrage, UV et matériaux ; inspecter Asset Doctor.
- [ ] Identifier la version TRELLIS des workflows déjà installés, le nœud image, le nœud d'export et le chemin GLB produit.
- [ ] Tester `inspect-glb` sur une sortie réelle ; normaliser explicitement les transformations/matériaux/textures si le contrat refuse le fichier.
- [ ] Mesurer durée et VRAM du workflow existant sur RTX 5080, garder modèle/commit/workflow/seed et licence de chaque génération.
- [ ] Importer le candidat dans une carte de revue Unreal 5.8 : orientation, échelle cm, pivots, matériaux, UV, collisions, LOD/Nanite et performances.
- [ ] Approuver visuellement un objet, puis un module architectural avant utilisation dans le jeu existant.

**Encore à développer :** soumission/suivi/collecte automatique des workflows TRELLIS
via ComfyUI, ajustement automatique caméra/géométrie, génération multi-vues et
reconstruction neuronale intégrée. Le transfert local GLB et le worker Blender sont
implémentés ; les tests synthétiques ne qualifient pas les workflows GPU du PC.

État de référence : CryptoNyan Asset Studio **v0.24**, 22 octobre 2026.
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

## Revue réversible des matériaux dans les niveaux (v0.21)

Guide : [inspection, plan, comparaison, application et restauration](level-material-review.md).

- [ ] Activer Python/Editor Scripting Utilities, arrêter PIE, sauvegarder cartes et
  assets, télécharger LFS puis sélectionner un petit lot de composants du niveau.
- [ ] Vérifier l'inspection : GUID/chemins d'acteurs, classes, mesh, noms des slots,
  héritage des matériaux et overrides locaux. Tester refus des matériaux dynamiques,
  composants Construction Script/ISM/HISM, packages d’acteurs externes World Partition
  et acteurs d’un sous-niveau streamé.
- [ ] Préparer un plan de MIC sauvegardés, lire le HTML et effectuer le dry-run.
- [ ] Appliquer dans une copie de travail du niveau existant : vérifier rendu,
  notifications de modification, Undo/Redo, slots non ciblés et acteurs hors sélection.
- [ ] Restaurer avant sauvegarde et vérifier la liste d'overrides exacte, y compris
  cases nulles et liste vide. Modifier un slot à la main puis vérifier le refus de
  restauration concurrente sans toucher aux autres composants du lot.
- [ ] Tester application → sauvegarde/réouverture → restauration → sauvegarde/réouverture.
  Vérifier les GUID, le viewport et les matériaux hérités dans le niveau réel.
- [ ] Qualifier séparément le Mesh natif du Blueprint du personnage, ses resets de
  matériaux et les droits de sauvegarde. Les acteurs externes World Partition
  nécessitent encore un adaptateur distinct ; leur refus ne se lève pas par validation.
- [ ] Conserver un journal d'application interrompue ; vérifier la reprise explicite
  vers l'original. Ne pas imbriquer plusieurs revues sur les mêmes composants.
- [ ] Pour comparer visuellement, conserver caméra/frame/exposition/éclairage identiques ;
  le HTML compare des affectations, pas des rendus. Aucun score artistique automatisé.

## 9.20 — Niveaux riches, tenues et références ComfyUI (v0.20)

Guides : [niveaux et tenues](rich-levels-and-wardrobe.md),
[vêtements Blender](garment-workflow.md), [références ComfyUI](comfy-references.md).

- [ ] Adapter les trois recettes aux vrais assets, os, sockets, UV et action ;
  télécharger les fichiers Git LFS et sauvegarder les sources avant les plans.
- [ ] Exécuter `test_cryptonyan_garments.py` avec le Blender Windows installé ;
  comparer le vêtement candidat et le corps sur marche/course/saut, poses extrêmes,
  morph targets et LOD. Examiner les triangles et les frames non échantillonnées.
- [ ] Vérifier le corps/proxy fermé, les normales, l'alignement en pose de référence,
  les poids normalisés et les masques d'occupation UV. Importer le vêtement comme
  nouveau SkeletalMesh avec l'exporteur skeletal habituel, pas le publisher statique.
- [ ] Compiler le plugin v0.3 incluant `CryptoNyanMechanism` avec UHT/UnrealBuildTool 5.8.
  Les tests cloud compilent seulement ses règles indépendantes du moteur.
- [ ] Dans une carte de revue vide, placer le niveau : vérifier pivots/dimensions,
  ouvertures, raccords, escaliers manuels, passages, collisions et NavMesh.
- [ ] Jouer les six mécanismes avec le contrôleur réel : pouvoir correct/incorrect,
  activation unique, overlaps, sortie/destruction d'une zone, restauration gravité/
  friction, zones superposées, limites 30/60/120 FPS et refus du réseau.
- [ ] Relier `OnActivated` aux événements du jeu, puis tester les plateformes mobiles,
  leur phase, la montée du personnage et les distances de saut.
- [ ] Contrôler lumières, soleil, brouillard, sons et Niagara pour chaque ambiance ;
  mesurer CPU/GPU/VRAM et comparer les mêmes caméras. Sauvegarder/réouvrir la revue.
- [ ] Placer chaque tenue en carte séparée : slots, sockets, offsets, Leader Pose,
  poses de référence, clipping, LOD, lecture animée et absence de notifies/physique.
  Aucun menu d'inventaire ou de garde-robe du jeu n'est fourni par cette étape.
- [ ] Configurer un workflow API et des modèles ComfyUI locaux, les vrais IDs
  `LoadImage`, le dossier `input` et les connexions pour référence/UV/masque.
  Vérifier la conversion des masques RGB : MASK de LoadImage utilise l'alpha.
- [ ] Préparer le profil dérivé, lancer un prévol puis une texture et un petit lot.
  Vérifier fidélité, coutures UV, diversité, taille des motifs, reçus/hashes,
  modèles/nœuds installés et licences. Ne pas modifier les entrées en attente GPU.
- [ ] Après validation, créer les MIC candidates et les ajouter au catalogue de
  tenues ; tester l'adoption dans le jeu sur des copies et conserver les preuves.

## Corrections des poids sur une copie (v0.19)

Guide : [plan, candidat et vérification après réouverture](rig-repair.md).

- [ ] Refaire l'audit avec la v0.19 pour capturer verrous, mode, overrides et partage
  des données. Préparer un `.blend` autonome avec meshes indépendants en Object Mode.
- [ ] Choisir un budget d'influences et un plafond de poids supprimés. Examiner le
  plan, notamment les indices modifiés et les cas laissés entiers pour revue manuelle.
- [ ] Exécuter d'abord sans `--apply`, puis créer un candidat dans un dossier neuf.
  Vérifier le reçu, les hashes et le rapport issu de la réouverture du candidat.
- [ ] Exécuter la suite `test_cryptonyan_rig_repair.py` avec Blender Windows.
- [ ] Comparer source/candidat dans Weight Paint et sur les animations réelles :
  pattes, dos, queue, accessoires, poses extrêmes et shape keys. Consigner les défauts
  visuels même si les sommes de poids et budgets d'influences sont corrects.
- [ ] Si le candidat convient, tester son import sur un asset Unreal séparé ; vérifier
  squelette, poids importés et déformation en jeu avant toute adoption dans le projet.

## AnimSequence Unreal et poids du rig existant (v0.18)

Guide : [capture Unreal et Rig Doctor](rig-and-unreal-animation.md).

- [ ] Activer Python et les API d'animation éditeur dans Unreal 5.8. Reporter le chemin
  du clip et les vrais noms d'os ; lancer une première capture de 31 poses hors projet.
- [ ] Comparer trois poses au viewport, notamment une rotation non nulle. Vérifier
  centimètres/mètres, inversion de Y, durée, dernier échantillon et mouvement racine
  avec les options `enable_root_motion` et `force_root_lock` du clip.
- [ ] Vérifier les hashes animation/squelette avant/après. Confirmer que les contacts
  restent non évalués : le clip seul n'inclut pas la trajectoire d'acteur en jeu.
- [ ] Exécuter Rig Doctor avec Blender Windows sur une copie autonome du personnage.
  Contrôler dans Weight Paint les indices sans poids, sommes incorrectes et influences
  dépassant le budget choisi. Examiner séparément masques et os non déformants.
- [ ] Tester visuellement les déformations extrêmes, shape keys, IK et import Unreal.
  Ces éléments ne sont pas validés par l'audit des poids du mesh de base.
- [ ] Consigner version, commandes, résultats et hashes. Les tests Unreal automatisés
  sont des doubles d'API ; un test Python vert ne remplace pas l'essai dans l'éditeur.

## Animation Doctor — personnage existant (v0.16)

Guide et commandes PowerShell : [Animation Doctor](animation-doctor.md).

- [ ] Préparer un `.blend` autonome de travail avec le vrai rig et un clip ; si les
  animations existent uniquement en `.uasset`, utiliser la capture directe v0.18
  ci-dessus pour les poses du clip. L'audit des poids nécessite encore un `.blend`.
- [ ] Reporter les vrais noms armature/action/racine/os et la plage du clip dans le
  JSON. Vérifier `scale_length`, fps et pose finale de boucle. Avec Blender 4.4+,
  vérifier l'affectation du slot choisi ; le cloud a testé Blender 4.3.2.
- [ ] Exécuter les tests avec `LOOPCUT_BLENDER` pointant vers Blender Windows.
  Comparer une position issue des contraintes/IK à l'éditeur au même frame.
- [ ] Auditer marche/course puis saut/dash avec des seuils adaptés. Comparer les
  avertissements à la lecture visuelle ; comparer les hashes source avant/après.
- [ ] Déclarer les appuis après observation. Garder `contact_space: unknown` si la
  trajectoire mondiale du personnage manque. Vérifier qu'aucun résultat non évalué
  n'est interprété comme une absence de glissement.
- [ ] Comparer les repères de `events.json` au contact réel des pattes dans Unreal,
  après retargeting, blending et déplacement du Character. Animation Doctor ne crée
  pas d'effet ; le Creative Director v0.17 ci-dessous fournit le premier adaptateur.

Restent à développer : audit des poids/déformations sur rig arbitraire, correction
sur copie, sampler Unreal et mesure des contacts sur supports mobiles. La v0.17
ci-dessous ajoute des effets sur copie, des cutscenes de caméras et un placement
de modules en carte de revue ; leur intégration finale au jeu reste locale.

## Effets, cutscenes et architecture — Creative Director (v0.17)

Guide et exemples : [Creative Director](creative-director.md). Les adaptateurs sont
implémentés ; les tests cloud utilisent des doubles d'API Unreal. Les points ci-dessous
exigent ton vrai éditeur 5.8, les assets Git LFS et les plugins éditeur correspondants.
La v0.17 remplace la mention « adaptateur AnimNotify/Niagara à développer » de la v0.16
par un premier adaptateur de copie d'AnimSequence ; le sampler direct Unreal reste à faire.

- [ ] Préparer un plan hors projet avec les vrais chemins d'assets. Vérifier le refus
  d'un plan dont une source ou un sidecar a changé, avant création de candidat.
- [ ] Exécuter le dry-run, puis appliquer dans le bon projet avec le contenu sauvegardé.
  Vérifier le reçu, le nouveau dossier et les hashes des originaux après exécution.
- [ ] Effets : vérifier le Skeleton et les sockets, ouvrir `AN_Directed`, comparer les
  notifies d'origine et la nouvelle piste. Activer la prévisualisation des effets sur la
  copie si souhaité ; par défaut, ils ne se déclenchent pas dans l'éditeur d'animation.
- [ ] Tester un Niagara one-shot en PIE : appui/dash/atterrissage, boucle, changements
  de vitesse, blend/transitions et absence d'effets doublés. Vérifier durée, orientation,
  échelle, coût GPU et comportement attaché/détaché. Le choix par surface reste à développer.
- [ ] Contacts importés : comparer la trace Blender à l'AnimSequence retargetée et au
  déplacement réel. Un contact inconnu/glissant doit être refusé à l'import automatique.
- [ ] Cutscene : ouvrir `LS_Directed`, vérifier caméras spawnables, première/dernière
  frame de chaque plan, Camera Cuts, échelle cm et interpolation. Ajuster lentille,
  focus, exposition et cadrage dans Sequencer ; vérifier que la carte n'est pas sauvegardée.
- [ ] Architecture : créer/ouvrir la carte de revue vide demandée, placer les modules,
  examiner pivots, pas, matériaux, intersections, collisions, navigation et performances.
  Sauvegarder manuellement après revue, puis intégrer sur une copie du niveau existant.
- [ ] Sur un plan de test, provoquer un échec de placement. Vérifier les acteurs retirés
  et ceux éventuellement restants dans le reçu avant de relancer avec une nouvelle destination.

Restent à développer : trajectoires d'acteur/poses en PIE, reconstruction générale du rig
et attribution des poids manquants (les captures de clips et corrections bornées sur
copie sont disponibles en v0.18–v0.19),
effets dynamiques par surface et anti-doublon runtime, création de graphes Niagara,
déclenchement/skip des cutscenes avec restitution des contrôles, rendu vidéo automatisé,
architecture PCG/HISM et placement validé dans les niveaux de production.

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
  cause d'exécutable introuvable. À la v0.15, la suite contient 297 cas, dont 20 tests
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
- [ ] Tester une [collection v0.15](texture-collections.md) de deux petites textures :
  plan hors ligne, `advance`, redémarrage du MCP, même prompt ID, collecte, entrée
  suivante et index final. Vérifier qu'aucun deuxième calcul n'est lancé pour une
  entrée déjà soumise et que les fichiers du jeu restent inchangés.
- [ ] Comparer la palette, l'échelle des motifs, les UV et les normales des candidats
  sur des copies Unreal. Le style commun et les seeds ne garantissent pas la cohérence
  visuelle ni une reproduction exacte entre versions de modèles/GPU. Mesurer la VRAM.
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
