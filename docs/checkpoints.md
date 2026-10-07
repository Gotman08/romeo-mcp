# Checkpoints et reprises verifiees

[Documentation](README.md) · [Catalogue](Tools.md) · [Observations](observability.md)

Ce contrat conserve le format de sauvegarde du programme : fichiers binaires,
JSON, HDF5, checkpoints de solveur ou de modele. Il ajoute un manifeste commun
et des preuves applicatives. Un programme doit participer au protocole ; Romeo
ne peut pas extraire universellement son etat en memoire.

## Ce que les preuves etablissent

| Preuve | Signification |
|---|---|
| `submitted` | Slurm a accepte la soumission, pas necessairement demarre le job. |
| `scheduler.state` | Etat observe avec Slurm, independant des preuves applicatives. |
| `checkpoint.integrity_verified` | Tous les fichiers declares ont leur taille et SHA-256 attendus. |
| `loaded_ranks` | Rangs qui declarent avoir effectivement charge le checkpoint selectionne a l'etape attendue. |
| `progressed_ranks` | Rangs qui declarent ensuite une nouvelle etape utile du calcul. |
| `runtime.resume_validated` | Tous les rangs ont fourni les deux preuves pour la meme tentative et le meme checkpoint. |
| `checkpoint_after_signal_verified` | Checkpoint coherent associe a la demande de signal, avec acquittement de tous les rangs a la meme etape. |
| `application_completion_observed` | Tous les rangs declarent la meme etape finale ; le superviseur controle aussi la sortie du programme. |
| `result_validated` | Reste faux pour le calcul generique : aucune validation scientifique des sorties n'est inventee. |
| `independent_backup` | Devient vrai pour un export verifie sur la machine du client MCP, hors de la cible SSH ROMEO. |

Les preuves loaded/progress proviennent de l'application. Les empreintes lient
la sauvegarde a la commande, aux fichiers de programme et de donnees declares,
a l'architecture, aux empreintes Spack chargees et au releve MPI demande.
Declare toutes les entrees influencant le calcul, y compris configurations,
graines, bibliotheques et extensions pertinentes. Ce contrat ne deduit pas
automatiquement toutes les dependances ni toutes les variables d'environnement.

Une preuve persiste apres coupure SSH. Son age est affiche ; la presence d'un
heartbeat ne prouve pas que le processus vit encore. Consulte aussi Slurm.
Le travail effectue depuis le dernier checkpoint peut devoir etre refait.

## Preparer une chaine

`job_resilient_prepare` accepte la topologie MPI et le contrat optionnel :

```json
{
  "name": "solveur",
  "command": "/scratch_p/VOTRE_IDENTIFIANT/code/solveur --input donnees.dat",
  "workdir": "/scratch_p/VOTRE_IDENTIFIANT/code",
  "arch": "x64cpu",
  "gpus_per_node": 0,
  "nodes": 2,
  "ntasks_per_node": 4,
  "cpus_per_task": 8,
  "distributed": "mpi",
  "cpu_bind": "cores",
  "segment_time": "1h",
  "max_total_time": "4h",
  "checkpoint_dir": "/scratch_p/VOTRE_IDENTIFIANT/ckpts",
  "checkpoint_contract": {
    "code_files": ["/scratch_p/VOTRE_IDENTIFIANT/code/solveur"],
    "data_files": ["/scratch_p/VOTRE_IDENTIFIANT/code/donnees.dat"]
  }
}
```

Le plan rend son `run_id`, cree par defaut aleatoirement pour isoler les calculs.
Soumettre avec `job_resilient_submit(plan_id, confirm=true)`. Les segments sont
ordonnes avec `afterany` et partagent les fichiers auxiliaires scelles, deposes
une seule fois. Un marqueur `TERMINE` historique n'est jamais une preuve dans ce
mode. Sans contrat, le mode historique est conserve avec un avertissement.

| Champ du contrat | Defaut / regle |
|---|---|
| `run_id` | Identifiant aleatoire. Reutiliser uniquement pour le meme calcul. |
| `code_files` | Obligatoire, au moins un fichier de programme ; chemins absolus. |
| `data_files` | Liste vide ; au plus 128 fichiers de programme/donnees au total. |
| `world_size` | Deduit du lanceur ; doit correspondre aux rangs applicatifs. |
| `require_resume` | Faux au premier lancement ; vrai dans `job_resume_prepare`. |
| `max_input_bytes`, `max_checkpoint_bytes` | 1 Tio chacun ; budgets configurables. |
| `verification_timeout_seconds` | 900 s ; inclut hachages/copies selon la phase. |
| `resume_timeout_seconds` | 120 s pour observer chargement et progression. |
| `runtime_python` | `python3`, ou chemin absolu d'un interpreteur disponible sur les noeuds. |
| `backup_dir` | Aucune copie de conservation par defaut. |
| `quota_filesystem`, `quota_fileset`, `quota_group` | `gpfs` ; fileset obligatoire pour une copie, groupe facultatif. |
| `keep_last` | 3 generations source valides, minimum 2. Aucune suppression sans copie encore verifiee. |

Les champs `action` et `expected_binding_sha256` servent aux plans de protection
et de reprise ; ces outils les fixent automatiquement a partir du job conserve.
Les gros hachages et copies restent dans une allocation de calcul.

## Adapter le programme

Romeo exporte `ROMEO_CHECKPOINT_DIR`, `ROMEO_RUN_ID`,
`ROMEO_CHECKPOINT_ATTEMPT`, `ROMEO_RESUME_MANIFEST`, `ROMEO_RESUME_SHA256` et
`ROMEO_RESUME_STEP`. Le contexte JSON de la tentative contient le binding
exact a reporter dans le manifeste. `PYTHONPATH` inclut le module stdlib
`checkpoint_protocol`, sans dependance MCP sur les noeuds.

1. Au demarrage, charger les fichiers du manifeste selectionne si
   `ROMEO_RESUME_MANIFEST` est non vide. Chaque rang emet `loaded` avec
   l'etape effectivement chargee, puis `progress` apres une nouvelle etape utile.
2. Le gestionnaire SIGUSR1 pose un drapeau. Les appels MPI et la sauvegarde
   se font dans le flux normal du programme, apres un point de coherence commun.
3. Ecrire les fichiers dans `CHECKPOINT_DIR/run_id/generation-N`, avec `N`
   sur 20 chiffres. Fermer les fichiers et synchroniser tous les rangs.
   Chaque rang emet `signal_ack` a l'etape sauvegardee pour une sauvegarde demandee.
4. Un coordinateur publie `manifest.json` en dernier avec la couverture des
   rangs et les etapes reellement rassemblees. Une generation publiee est immuable.
5. Quand tout le calcul est termine, chaque rang emet `completed` avec la meme
   etape finale. Le programme sort avec 0. Une sortie 0 seule ne marque pas le
   calcul termine et ne permet pas d'ignorer les segments suivants.

En Python, utiliser `application_context`, `generation_directory`, `publish`
et `record_event` du [module de protocole](../romeo_mcp/checkpoint_protocol.py).
L'[exemple de compteur](../examples/checkpoint_counter.py) fonctionne en serie
et avec `--mpi` si mpi4py est deja installe dans l'environnement selectionne.

C, C++, Fortran et les autres langages peuvent produire les memes JSON et
utiliser la passerelle CLI :

```bash
"$ROMEO_CHECKPOINT_PYTHON" "$ROMEO_CHECKPOINT_HELPER" event loaded 42 --rank 0
"$ROMEO_CHECKPOINT_PYTHON" "$ROMEO_CHECKPOINT_HELPER" event progress 43 --rank 0
"$ROMEO_CHECKPOINT_PYTHON" "$ROMEO_CHECKPOINT_HELPER" event signal_ack 43 --rank 0
"$ROMEO_CHECKPOINT_PYTHON" "$ROMEO_CHECKPOINT_HELPER" publish publication.json
```

`publication.json` contient `generation`, `step`, `files` (chemins relatifs et
liste `ranks` pour chaque fichier), et `rank_steps` (etapes rassemblees par le
programme). Le helper prend le calcul, le nombre de rangs et le binding dans
le contexte de tentative ; il calcule les SHA-256 et publie atomiquement.
Les rangs indiques doivent etre ceux du communicateur/de l'application.

Le superviseur transmet SIGUSR1 a srun, puis chaque proxy de rang le transmet
au groupe de processus applicatif. Les descripteurs PMI sont conserves.
L'acquittement du proxy et celui du programme sont distincts. Ce dispositif
reprend un job entier depuis un checkpoint ; il ne remplace pas ULFM ou un
protocole applicatif de reparation d'un communicateur MPI en cours d'execution.

## Reprendre un job arrete

`checkpoint_inspect(job_id)` liste les manifestes et leurs declarations, sans
certifier les fichiers. `job_resume_prepare(job_id)` conserve la commande et
la topologie du job termine, et fige l'association au programme/donnees
observee pour ce job. `job_resume_submit` soumet le plan exact.

Le noeud selectionne la plus recente generation complete, compatible et dont
les fichiers ont ete verifies. Les generations partielles ou corrompues sont
signalees ; une generation anterieure valide peut etre choisie. Si aucune
generation compatible n'existe, le calcul refuse de repartir a zero.
`job_resume_status` expose Slurm et les preuves applicatives. Une tentative
concurrente est refusee par un verrou OS, libere aussi apres SIGKILL.

`job_checkpoint_request(job_id)` demande une sauvegarde a un job RUNNING
supervise. Attendre `runtime.checkpoint_after_signal_verified=true` avant
d'arreter le calcul. La demande elle-meme ne certifie aucun fichier.

## MPI, OpenMP et ressources Slurm

`distributed="openmp"` impose une tache sur un noeud ; `cpus_per_task` fixe
`OMP_NUM_THREADS`, `omp_places` et `omp_proc_bind` precisent le placement.
Le mode MPI conserve les rangs par noeud et permet un calcul hybride OpenMP.
Les plans acceptent aussi `reservation`, `gpus_per_task` et `gpu_bind`
(`single:1`, `closest`, `map_gpu:...`). Les quantites GPU incoherentes sont refusees.

`romeo_software` conserve les noms habituels et ajoute `specifications` :
versions, compilateurs (y compris les dependances de compilateur Spack 1.x),
variantes, architectures et empreintes. Utiliser `load_spec="/hash"` pour
selectionner une installation precise.

`mpi_environment` accepte `provider` (`openmpi` sur x64cpu, `hpcx` sur armgpu),
`executable` (binaire ELF absolu), et facultativement `spack_hash`, `compiler`
(`gcc@11.4.1`, par exemple) et `library_sha256`. Le noeud controle l'architecture,
les bibliotheques manquantes, le fournisseur et la libmpi effectivement liee
par rapport au wrapper mpicc selectionne. Le releve est accessible avec
`job_environment_status`. Les binaires statiques, les chargeurs MPI dynamiques
indirects et les conteneurs demandent un adaptateur ; aucune compatibilite ne
leur est attribuee sans preuve. Les collectives MPI ne sont pas testees par ldd.

## Conservation et copie independante

Avec `backup_dir`, le superviseur copie les checkpoints verifies avant de
pruner les generations source. Les quotas de blocs **et d'inodes**, `in_doubt`
et les delais de grace sont controles avant copie. Un quota illisible,
une copie interrompue ou un checksum incorrect empechent la suppression.
Les generations partielles ne prennent pas la place des generations valides
dans la retention. Les copies de conservation ne sont pas supprimees
automatiquement ; suivre leur quota et organiser leur archivage.

`checkpoint_protect_prepare` puis `checkpoint_protect_submit` protegent un
checkpoint existant sans relancer le programme, dans un petit job de la meme
architecture. Le fileset exact et, pour le projet, le groupe viennent de
`romeo_quota`.

Une copie dans un autre repertoire ROMEO partage encore les risques du centre.
`checkpoint_export_prepare(job_id, local_path)` prepare le telechargement dans
`local_path/run_id/generation-N`. Appeler `transfer_start`, puis
`checkpoint_export_status` : la machine du client verifie le manifeste fige
et chaque fichier, sans gros hachage sur le noeud de connexion. Une preuve
locale conservee est datee ; `refresh=true` reverifie les fichiers actuels.
Cela ne remplace pas votre politique d'archivage hors site.

Sources : [MPI ROMEO](https://romeo.univ-reims.fr/documentation/ressources/romeo_2025/utiliser_openmpi/),
[Spack ROMEO](https://romeo.univ-reims.fr/documentation/ressources/romeo_2025/charger_ses_logiciels/),
[soumission ROMEO](https://romeo.univ-reims.fr/documentation/ressources/romeo_2025/lancer_un_calcul/),
[stockage ROMEO](https://romeo.univ-reims.fr/documentation/ressources/romeo_2025/espaces_de_stockage/),
[signaux srun](https://slurm.schedmd.com/srun.html#SECTION_SIGNALS-AND-ESCAPE-SEQUENCES).
