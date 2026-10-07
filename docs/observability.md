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

`romeo_status` relit le cluster par défaut. `max_age_seconds=5` permet de
réutiliser une observation récente ; la réponse annonce `cached=true`, son âge
et `current_state_observed=false`. Une lecture partielle ou un échec ne produit
pas un cluster vide prétendument sain.

Une écriture SSH interrompue peut avoir atteint le shell distant : le transport
ne rejoue pas automatiquement une commande susceptible d'avoir des effets.
Les sondes explicitement déclarées en lecture seule peuvent reconnecter une fois.
Une expiration du délai n'est pas rejouée. Un plan de soumission interrompu
conserve `submission_outcome=unknown`, `retry_safe=false` et un état `uncertain`.

## Jobs et services après reconnexion

`job_status` interroge la comptabilité après sortie de la file, et le démarrage
estimé uniquement pour un job en attente. Il conserve les observations datées
dans le registre SQLite, avec leur cible. Après échec SSH, `ok=false` et
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
```

Les tests simulent SSH/Slurm et utilisent des processus locaux jetables pour
vérifier l'annulation. Ils ne soumettent aucun job et ne transfèrent aucun fichier
sur le cluster. Les gains de latence réelle restent à mesurer avec les compteurs
du MCP sur une charge représentative.
