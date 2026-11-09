# Observations, mesures et opérations longues

[Documentation](README.md) · [Catalogue Tools](Tools.md)

## Choisir et mesurer

`romeo_capabilities(task="jobs")` propose les outils utiles et indique leur
visibilité dans le profil courant. Cette lecture locale ne certifie ni SSH ni
les ressources disponibles. `mcp_diagnostics` affiche les durées agrégées du
démarrage, des outils, des commandes SSH, de l'attente du verrou et des réponses,
ainsi que les connexions lancées et les compteurs de caches. Aucun argument,
script ou résultat n'est conservé dans ces compteurs.

## Fraîcheur et transport

Les identités et racines SSH sont partagées entre lectures concurrentes et
invalidées après fermeture, réinitialisation ou nouvelle connexion.

Le cache Spack est borné à huit catalogues, identifiés par hôte, utilisateur et
architecture. `romeo_software` accepte `max_age_seconds=300` par défaut, jusqu'à
3600, et `refresh=true` pour relire. Une réponse tronquée, vide ou en échec
n'est pas mémorisée. `observation` indique l'âge et l'origine cache/lecture.

`romeo_status` réutilise un relevé de moins de 30 secondes par défaut ;
`max_age_seconds=0` force une nouvelle lecture. La réponse réutilisée annonce
`cached=true`, son âge et `current_state_observed=false`. Une lecture partielle
ou un échec ne produit pas un cluster vide prétendument sain.

Une écriture SSH interrompue peut avoir atteint le shell distant : le transport
ne rejoue pas automatiquement une commande susceptible d'avoir des effets.
Les sondes explicitement déclarées en lecture seule peuvent reconnecter une fois.
Une expiration du délai n'est pas rejouée. Un plan de soumission interrompu
conserve `submission_outcome=unknown`, `retry_safe=false` et un état `uncertain`.

## Jobs et services après reconnexion

`job_status` interroge la comptabilité après sortie de la file ; le démarrage
estimé d'un job en attente vient du même relevé `squeue`. Il conserve les
observations datées dans le registre SQLite, avec leur cible, et les réutilise
selon les règles de la [section suivante](#ménager-le-contrôleur-slurm). Après échec SSH, `ok=false` et
`last_observation` permettent de retrouver le dernier état sans le présenter
comme actuel. `job_observation_get` fonctionne localement après redémarrage ;
sa cible enregistrée reste visible et `target_checked=false` est explicite.

`submission_observed`, `scheduler_completed` et `result_validated` répondent
à trois questions distinctes. Slurm `COMPLETED` ne valide pas le résultat scientifique.
`scheduler_success_observed` exige aussi le code de sortie `0:0`.
Pour un tableau, une ligne d'allocation n'est pas un verdict sur tout le tableau :
`allocation_id` et `scope=matching_allocation` explicitent cette portée.

`cancel_job` enregistre `CANCEL_REQUESTED`, puis `job_status` observe l'arrêt.
Un accusé de réception `scancel` ne suffit pas à annoncer `CANCELLED`.
Les services conservent également leur dernière observation ; `ready` exige
toujours une sonde HTTP concluante, au-delà de l'état Slurm `RUNNING`.

## Ménager le contrôleur Slurm

Chaque `squeue`, `sinfo`, `sshare`, `sstat` ou `scontrol` est une requête au
contrôleur Slurm, partagé par tous les utilisateurs de ROMEO ; `sacct` sollicite
la base de comptabilité, partagée elle aussi. Le serveur en émet le moins
possible :

| Lecture | Requêtes | Réutilisation |
|---|---|---|
| `job_status`, job en file | un `squeue` (démarrage estimé, cœurs et mémoire compris) | 20 s par défaut (`max_age_seconds`, jusqu'à 300, `0` pour relire) |
| `job_status`, job sorti de la file | un `squeue`, puis un `sacct` | état définitif réutilisé sans limite d'âge |
| `wait_for_job` | une lecture `job_status` par sondage | sondages espacés de 30 s, puis ×1,5 jusqu'à 120 s |
| `romeo_status` | un `sinfo`, un `sshare`, un `squeue` avec la file personnelle | 30 s par défaut |
| `suggest_submission_slot` | vue du parc, puis `squeue` de la file PENDING de tout le cluster | 60 s pour l'une et l'autre |
| `job_efficiency` | un `sacct` | relevé définitif réutilisé, `refresh=true` pour relire |
| `job_system_health` | `sstat` et une sonde `srun --overlap` | cœurs et mémoire repris de `job_status` |
| `job_energy_footprint` | `sacct` ; `scontrol show config` | configuration relue au plus une fois par heure |
| `romeo_selfcheck` | un `sinfo` et un `sacctmgr` | — |

Les états définitifs sont `COMPLETED`, `FAILED`, `CANCELLED`, `TIMEOUT`,
`OUT_OF_MEMORY` et `DEADLINE`. `PREEMPTED`, `NODE_FAIL` et `BOOT_FAIL` en sont
exclus : Slurm peut remettre le job en file. Les observations de `job_status` et
`job_efficiency` résident dans le registre local : plusieurs sessions MCP de la
même machine les partagent. `cancel_job`, `job_checkpoint_request` et
`service_stop` invalident celles du job et de tout son tableau ; la lecture
suivante interroge Slurm. Les caches de `romeo_status` et de la file PENDING sont
propres à chaque processus. Une réponse réutilisée annonce toujours
`cached=true`, son âge et `current_state_observed=false`.

Pour un job en attente, une consultation toutes les quelques minutes suffit :
`wait_for_job` sert aux calculs courts. Les sondes `job_live_metrics`,
`job_system_health` et `job_stack_trace` créent chacune une étape Slurm ; elles
servent à un relevé ponctuel, pas à une surveillance en boucle.

## Transferts en arrière-plan

1. `transfer_prepare(direction="upload", local_path="results.dat", remote_path="/scratch/VOTRE_UTILISATEUR/results.dat")`
   conserve un plan local contenant la cible et les chemins exacts.
2. Relire le plan, puis `transfer_start(transfer_id=..., confirm=true)` consomme
   ce plan une fois et lance un processus détaché. Le plan expire après 24 heures.
3. `transfer_status` relit progression et journal borné, même après reconnexion.
4. `transfer_cancel(transfer_id=..., confirm=true)` demande l'annulation.

Remplacer les chemins et identifiants d'exemple par ceux de votre configuration.

Les outils synchrones `upload_to_romeo` et `download_from_romeo` restent disponibles.
Les nouveaux transferts utilisent les mêmes transports et contrôles d'intégrité.
`completed` certifie un contrôle de fichier réussi ; `completed_unverified`
indique une copie achevée sans intégrité établie, notamment pour les répertoires.
Une copie peut remplacer le fichier cible : relire les chemins avant confirmation.

Le worker publie un heartbeat pendant le processus de copie. Les sondes SSH et
le calcul d'empreinte peuvent retarder le traitement d'une annulation pendant
la vérification. Un heartbeat ancien laisse `liveness=unverified` ; le MCP ne
relance jamais automatiquement un transfert dont le démarrage est incertain.
L'annulation peut laisser des fichiers partiels ; ils ne sont pas supprimés.
Elle arrête le processus de copie possédé par le worker ; l'arrêt de ses
descendants reste `descendants_stopped_verified=false`.
Rsync peut réutiliser ses données partielles lors d'un nouveau transfert approuvé ;
aucune reprise automatique après interruption n'est promise.

Les plans, journaux et statuts résident à côté du registre, dans `transfers/`.
Les lecteurs reçoivent uniquement des objets JSON complets ; le remplacement
atomique tolère les brèves ouvertures concurrentes sous Windows.

## Vérification hors ligne

```sh
python tests/run_all.py --only observability
python tests/run_all.py --only slurm-economy
```

La suite `slurm-economy` exécute les commandes exactes du serveur avec Bash, des
fonctions tenant lieu des binaires Slurm, et compte chaque appel émis.

Les tests simulent SSH/Slurm et utilisent des processus locaux jetables pour
vérifier l'annulation. Ils ne soumettent aucun job et ne transfèrent aucun fichier
sur le cluster. Les gains de latence réelle restent à mesurer avec les compteurs
du MCP sur une charge représentative.
