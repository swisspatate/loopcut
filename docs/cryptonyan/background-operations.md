# Traitements Studio en arrière-plan — v0.32

Depuis v0.33, [les parcours Studio](studio-workflows.md) peuvent relier plusieurs
opérations dans un seul job de cette file. Le suivi inclut l'étape en cours et ses
critères ; une erreur ou une annulation bloque toutes les étapes suivantes.

L'agent peut maintenant lancer une opération longue sans attendre la fin de Blender
pour recevoir une réponse MCP. La file réutilise les **18 opérations existantes**,
leurs recettes et leurs contrôles de sources. Aucun modèle ou compte supplémentaire
n'est nécessaire. Mettre à jour le dépôt et reconnecter le serveur MCP ; les profils
`connection.json` existants restent valides.

## Parcours

1. `studio_route`, puis `studio_guide` pour découvrir le parcours et ses vrais paramètres.
2. `studio_submit` avec un identifiant stable, une opération autorisée et ses arguments.
3. `studio_operation` pour suivre cet identifiant ; espacer les lectures, par exemple
   0,5 s, 1 s, 2 s puis jusqu'à 5 s. Le serveur n'envoie pas de notifications de progression.
4. Si `succeeded`, lire les rapports et images par `studio_artifact`. Inspecter les
   résultats métier : une exécution terminée ne signifie pas un audit sans défaut.
5. `studio_cancel` pour demander l'arrêt ; attendre un état terminal.
   `studio_jobs` avec `{"limit": 20}` retrouve les opérations récentes après reconnexion.

Exemple d'appel **à `studio_submit`**, après avoir préparé le programme caméra :

```json
{
  "request_id": "camera-preview-001",
  "operation": "camera_preview",
  "arguments": {
    "bundle": "work:studio/operations/camera-program-001/output"
  }
}
```

La réponse initiale porte `status: "queued"`. Le lancement peut déjà avoir commencé
au moment où l'agent la reçoit ; consulter le reçu actualisé. Une fois l'opération
terminée, le manifeste contient les chemins, tailles et SHA-256 des fichiers.
Les handles et les schémas détaillés restent ceux du [guide de routage](agent-routing.md).

`studio_execute` reste disponible pour les petits traitements synchrones. Il utilise
la même file : il peut donc attendre une opération déjà en cours. Pour les opérations
longues ou une file occupée, préférer `studio_submit`.

## États durables

| État | Signification |
| --- | --- |
| `queued` | Accepté et enregistré, en attente du worker. |
| `running` | Worker actif ; `phase` vaut `operation` ou `indexing`. |
| `cancelling` | Arrêt demandé, mais le worker peut encore être actif. |
| `succeeded` | Parcours et indexation terminés ; artefacts accessibles et vérifiés. |
| `failed` | Erreur conservée ; aucune relance automatique. |
| `timed_out` | Un contrôle a détecté le dépassement du budget Studio ou du worker. |
| `cancelled` | Travail arrêté ou annulé avant démarrage ; sorties partielles non publiées. |
| `interrupted` | Un redémarrage a trouvé une opération inachevée ; inspection nécessaire. |

Les horodatages indiquent l'acceptation, le début, la demande d'annulation et la fin
quand ces événements existent. Il n'y a pas de pourcentage estimé : la phase décrit
ce que le service sait réellement. `studio_jobs` donne les comptes de tous les états
et jusqu'à 100 reçus récents ; ces résumés ne vérifient pas les artefacts. Utiliser
`studio_operation` pour vérifier le manifeste d'une opération terminée.

## Annulation et fermeture

Une demande en attente est annulée sans exécution et libère une place dans la file.
Pour Blender, le contrôle d'annulation atteint le `run_process` existant, même si
le module a construit son propre `ExecutionContext`. Celui-ci arrête le groupe de
processus POSIX ou utilise `taskkill /T /F` sous Windows, puis attend la fin du processus.
Les workers conservent leur environnement isolé et leurs délais propres.

Les opérations Python et les copies/hashes de fichiers coopèrent aux frontières des
étapes et pendant l'indexation. Elles ne sont pas interrompues de force au milieu
d'une écriture ou d'un appel natif. L'état peut donc rester `cancelling` jusqu'à la
fin de cette étape. Ne pas annoncer un arrêt tant que le reçu n'est pas terminal.
Un résultat calculé juste avant l'annulation reste une sortie partielle : il n'est
pas publié comme artefact terminé.

La fermeture normale du serveur annule sa file, demande l'arrêt du travail actif
et conserve le verrou de propriétaire jusqu'à la fin des workers. Une fermeture
brutale ou une panne de machine ne suit pas ce protocole : au redémarrage, les reçus
`queued`, `running` et `cancelling` deviennent `interrupted`, **sans reprise**.
Ce statut ne prouve pas l'arrêt des anciens processus Blender. Vérifier les processus
locaux et les sorties partielles avant de choisir une nouvelle tentative.

## Identifiants, sources et budgets

- Un identifiant est commun à `studio_submit` et `studio_execute`. Après une réponse
  perdue, renvoyer **le même identifiant, la même opération et les mêmes arguments**.
  Une requête existante ne redémarre pas, même après un échec ou une interruption.
- L'identité couvre les paramètres et le contexte configuré, pas une capture instantanée
  du contenu des fichiers lors de la soumission. Les chemins sont contrôlés à l'acceptation
  puis au démarrage ; les modules existants effectuent leurs copies et contrôles de source.
  Éviter de modifier les sources pendant une opération en attente ou en cours.
- Les arguments sont copiés avant la mise en file. Un changement de configuration
  pendant l'attente fait échouer l'opération avant sa délégation.
- Un worker Studio et au maximum **16 opérations en attente ou actives** par workspace
  client ; **600 secondes** de budget d'exécution, contrôlé de façon coopérative,
  sans compter l'attente. Les délais Blender propres aux modules restent applicables
  (180 s pour les appels exposés). Une étape CPU peut dépasser le budget avant le
  prochain contrôle.
- Historique limité à 1 024 identifiants ; limites existantes de 2 048 fichiers et
  2 Gio par résultat. Aucune suppression automatique des résultats ni relance automatique.

Les profils Claude/Codex, la file `mission_*` et ComfyUI restent indépendants.
Cette file ne coordonne pas le GPU entre plusieurs clients ou services ; elle ne
soumet pas de nouveaux workflows ComfyUI. `mission_cancel` ne remplace pas
`studio_cancel`. Les scripts Unreal restent des handoffs inertes à lancer dans
une session d'éditeur locale après lecture.

## Preuves et validations locales

Les tests comprennent une vraie conversation stdio avec le lanceur exporté, des
requêtes concurrentes, l'annulation en attente/en calcul/en indexation, la saturation,
les délais, les reprises sans relance et l'arrêt d'un processus Python avec un enfant.
Sur Linux avec Blender 4.3.2, ils exécutent réellement une préparation/preview caméra
et annulent une fixture Blender volontairement longue après la sauvegarde d'une
copie partielle. Cette fixture remplace seulement la charge caméra pour tester l'arrêt.

Les contrôles CI Windows utilisent Python et `taskkill` ; ils ne qualifient pas un
Blender Windows installé ni les décisions d'un modèle Claude/Codex externe. Vérifier
ces parcours sur le PC avec un vrai asset. Unreal 5.8, les workflows/modèles ComfyUI
et le partage du GPU restent à qualifier localement :
[checklist centralisée](local-pc-checklist.md).
