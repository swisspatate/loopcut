# Inspecter et réutiliser des étapes — v0.34

L'agent peut diagnostiquer un parcours échoué et **réutiliser explicitement ses
premières étapes réussies** dans un nouveau parcours. Cela économise par exemple
un audit Blender ou la préparation des cartes PBR quand seule l'étape suivante
doit être corrigée. Les opérations et la file existantes sont réutilisées.

## Parcours depuis Claude Code ou Codex

1. Attendre un état parent `succeeded`, `failed`, `cancelled` ou `timed_out` avec
   `studio_operation`. Une annulation demandée n'est pas encore un arrêt confirmé.
2. Appeler `studio_workflow_inspect {"request_id": "essai-1"}`. La réponse donne
   un `workflow` sans reprise préconfigurée, les critères par étape, les manifests
   vérifiés et `reusable_prefix_steps`. Au maximum 32 entrées sont affichées par
   manifeste ; le contrôle porte sur l'ensemble des fichiers capturés.
3. Lire le diagnostic avec `studio_workflow_step_artifact`, par exemple :

   ```json
   {"request_id": "essai-1", "step_id": "audit", "file": "result.json"}
   ```

   Les fichiers sont relatifs au journal de l'étape : `result.json`, ou
   `output/reference.png` pour un Image Workshop préparé. JSON/texte : 256 Kio ;
   PNG : 2 Mio, rendu en image native MCP. `.blend` et GLB restent locaux.
   Un résultat ayant rejeté un critère est lisible si sa capture est complète,
   mais il ne peut pas être réutilisé comme étape réussie.
4. Corriger seulement les étapes après le préfixe retenu. Appeler
   `studio_workflow_fork` avec `source_request_id`, le `workflow` corrigé et
   `reuse_steps` entier de 1 à 8. Le préfixe doit garder exactement les mêmes
   identifiants, opérations, arguments et critères. Ne pas fabriquer le champ
   `reuse` : l'outil ajoute les identités et hashes des reçus réels.
5. L'outil prépare un plan sans exécuter. Soumettre son `workflow` avec
   `studio_submit`, `operation: "workflow_run"` et un **nouveau** `request_id`.
   Suivre ce nouvel identifiant jusqu'au résultat terminal.

Une réponse perdue après soumission demande au contraire de réutiliser le même
identifiant avec les mêmes arguments, pour retrouver le travail déjà soumis.

## Ce que signifie « réutilisé »

Le reçu montre `reused` et compte l'étape dans `completed_steps` et `reused_steps`.
Son dossier contient un reçu et une note de référence, sans nouvelle copie de son
ancien `.blend` ou de ses cartes. Les liaisons suivantes désignent les véritables
sorties conservées. `studio_workflow_step_artifact` suit cette provenance et lit le
rapport original ; `studio_artifact` sur le nouveau journal lit la note de référence.

Les références conservent l'identité de la demande, sa configuration, sa recette
et le hash du reçu. Avant admission, après attente dans la file, aux étapes et avant
promotion du résultat, tailles, hashes et ensemble de fichiers sont vérifiés.
La lecture d'un nouveau succès vérifie aussi ses ancêtres. Un fichier modifié,
ajouté, manquant ou remplacé par un lien bloque l'usage. Les fichiers réutilisés
comptent dans le budget cumulé de 2 048 fichiers / 2 Gio.

**C'est un snapshot conservé, pas un nouvel audit des sources actuelles.**
`snapshot_reuse_only: true` et `source_freshness_validated: false` le signalent.
Les sources d'origine peuvent avoir changé ou disparu si l'étape suivante travaille
uniquement sur cette capture. Pour examiner un personnage, niveau ou matériau modifié,
relancer les étapes concernées avec un parcours neuf. Les modules suivants conservent
leurs propres contrôles ; cette option ne force pas leur acceptation de sources obsolètes.

## Restrictions

- Aucun parcours actif ou `interrupted` ne fournit une reprise. Après arrêt brutal,
  examiner les processus Blender et repartir volontairement avec de nouveaux calculs.
- Seul un préfixe consécutif réussi est réutilisable. Un rejet, échec ou critère
  modifié exige de réexécuter cette étape ; aucune politique de réparation n'est déduite.
- La configuration de racines, Blender et projet doit correspondre à la capture
  pour une nouvelle exécution. La lecture historique reste possible sans cette concordance.
- Les scripts `unreal_handoff` sont régénérés pour leur nouvelle destination ;
  leur génération reste inerte, sans appel réseau ou exécution dans Unreal.
- Conserver tout l'historique référencé au même emplacement. Au maximum huit liens
  de provenance sont autorisés ; pour éviter une longue chaîne, repartir de la
  capture d'origine. Aucun nettoyage automatique n'est introduit.
- Les profils existants restent valides. Mettre à jour puis reconnecter le MCP pour
  découvrir les trois nouveaux outils. Voir [mise à jour Windows](updating-windows.md).

Les captures sans manifeste d'une ancienne étape échouée restent exclues. Les
anciennes étapes réussies munies d'un manifeste restent compatibles. Le schéma
`cryptonyan.studio-workflow/1` ajoute un champ optionnel `reuse` ; la CLI `validate`
contrôle sa structure uniquement, sans vérifier les fichiers de la file MCP.

La qualification cloud inclut des cartes PBR effectivement composées, un audit
Blender Linux suivi d'une copie de rig réparée/vérifiée et un client stdio réel.
Les essais sur ton personnage, Windows Blender, les clients IA et Unreal sont
suivis dans la [checklist PC](local-pc-checklist.md).
