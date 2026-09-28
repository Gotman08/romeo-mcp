# Référence technique

[Accueil](../README.md) › [Documentation](README.md) › Référence technique

[Outils](#outils-exposés) · [Jobs et journaux](#jobs-et-journaux) · [Calcul parallèle](#calcul-parallèle) ·
[Diagnostic](#diagnostic-des-échecs) · [Documentation locale](#documentation-hors-ligne) ·
[Conception du serveur](#partis-pris-de-conception)

Commandes à exécuter depuis la racine du dépôt. Les valeurs matérielles sont des relevés datés, à vérifier avec `romeo_selfcheck`.

## Outils exposés

Le profil `full` expose ce catalogue. Le profil `essential` en annonce 20 ;
`tool_profile_set` permet de changer de profil pendant la connexion. Voir les
[profils d’outils](configuration.md#profils-doutils).

**Contexte cluster**

| Outil | Rôle |
|---|---|
| `romeo_status` | Partitions, nœuds libres par architecture, file personnelle et fairshare, en un aller-retour SSH |
| `romeo_software` | Catalogue Spack de l'architecture demandée (mis en cache) |
| `romeo_modules` | Environment Modules, hérités de l'ancien calculateur |
| `romeo_quota` | Quotas réels via `mmlsquota`, avec alerte sur les délais de grâce expirés |
| `romeo_selfcheck` | **Confronte le modèle encodé au cluster réel** et rend les écarts (voir plus bas) |

**Jobs**

| Outil | Rôle |
|---|---|
| `job_prepare` / `job_submit` | Prépare et conserve le script exact ; soumet ce plan avec son `plan_id` et `confirm=true` |
| `job_array_prepare` / `job_array_submit` | Balayage paramétrique en tableau SLURM, une tâche par jeu de paramètres |
| `job_pipeline_prepare` / `job_pipeline_submit` | **Enchaînement d'étapes dépendantes** : préparer, calculer, rassembler. Ordonné, validé en entier avant la première soumission, architecture héritée |
| `job_status` | File d'attente, puis historique `sacct` ; démarrage estimé |
| `job_log_tail` / `job_log_search` | Dernières lignes des logs / recherche bornée avec un `pattern` obligatoire |
| `diagnose_job` | **Autopsie d'un échec en un appel** : état, journaux, causes reconnues, remèdes |
| `submit_resilient_job` | Chaîne de segments reprenables, pour dépasser la limite d'une partition rapide |
| `job_live_metrics` | **Télémétrie d'un job en cours** : occupation et VRAM des GPU, température, puissance |
| `job_stack_trace` | Pile d'appels d'un job bloqué (interblocage MPI, noyau CUDA figé) |
| `profile_job` / `profile_report` | Profilage Nsight Systems fenêtré, puis résumé des goulots |
| `job_energy_footprint` | Énergie et empreinte carbone : **modèle**, voir plus bas |
| `job_system_health` | Charge CPU face aux cœurs réservés, attente d'E/S, mémoire réelle |
| `sbatch_lint` | Vérifie un script **avant** l'envoi : CRLF, `--mem`, chemins, secrets |
| `job_efficiency` | Efficacité CPU/mémoire/GPU et recommandations de redimensionnement |
| `export_job_report` | [Fiche privée de reproductibilité](reproducibility.md) : script filtré, provenance, mesures Slurm et empreintes |
| `cancel_job`, `list_jobs`, `wait_for_job` | Gestion courante ; l’attente est plafonnée à 600 s |

**Construction et interactif**

| Outil | Rôle |
|---|---|
| `build_on_node` | Compile ou installe sur un nœud de l'architecture cible via `srun`. Indispensable pour aarch64 |
| `launch_interactive_service` | Lance JupyterLab, TensorBoard, vLLM ou MLflow sur un nœud et rend la commande de pont SSH |
| `allocate_debug_node` | Réserve un nœud pour de la mise au point interactive |
| `spawn_remote_workspace` | JupyterLab authentifié : jeton généré, tunnel et URL directe |
| `cluster_gpu_health_run` | Réserve des ressources GPU via `srun` et sonde bridage, ECC et fréquence ; mode NCCL désactivé |

**Stockage**

| Outil | Rôle |
|---|---|
| `storage_usage_audit` | Repère ce qui occupe l'espace ; propose les commandes, n'efface rien |
| `stage_dataset` | Télécharge depuis un nœud de calcul ; Hugging Face exige un venv `env_path` déjà préparé |
| `audit_orphan_files` | Fichiers volumineux abandonnés, répertoires de jobs morts |
| `secret_env_prepare` | Crée le dossier et le fichier distants, impose les droits 700/600, sans lire les secrets |
| `inject_io_staging` | Greffe la mise en cache en mémoire vive dans un script sbatch existant |

**Environnements et ordonnancement**

| Outil | Rôle |
|---|---|
| `build_wheel` | Compile une roue binaire aarch64 dans un dépôt local |
| `romeo_pip_install` | Installe dans un venv en réutilisant ces roues, sur la bonne architecture |
| `romeo_fairshare_forecast` | Effet d'une charge envisagée sur la part d'usage du compte |
| `suggest_submission_slot` | Quelle partition démarrerait le plus vite pour la taille visée |

**Fichiers** : `list_dir`, `read_remote_file`, `write_remote_file`,
`upload_to_romeo`, `download_from_romeo`.

**Documentation hors ligne** : `search_docs` (classement lexical par sections,
sources et lignes), `read_doc` (page ou plage de lignes, pagination sans perte).

**Échappatoire** : `run_login_command`, encadrée, avec un `allow_heavy` explicite
pour les cas que la documentation ROMEO autorise (par exemple un `pip install`
en environnement virtuel à destination du x86_64).

## Jobs et journaux

### Préparer puis soumettre le plan exact

`job_prepare` rend le script, les ressources, les avertissements, un `plan_id`,
son empreinte `plan_sha256` et sa date d’expiration `expires_at` (timestamp Unix).
Le plan est conservé dans le registre local privé `jobs.db` pendant au moins
24 heures ; il est soumettable seulement durant ces 24 heures. Aucun fichier
n’est écrit sur ROMEO à cette étape. Une lecture SSH peut résoudre les chemins.

Après vérification, appeler `job_submit(plan_id=..., confirm=true)`. Cet outil
n’accepte aucun nouveau paramètre de calcul : il utilise le script enregistré.
Pour modifier la demande, préparer un nouveau plan. Un changement de cible SSH,
de projet Slurm ou de racines impose aussi une nouvelle préparation.
Un aperçu dont les chemins sont illustratifs rend `submittable=false` et
`plan_id=null` ; reconnectez-vous ou configurez les racines, puis préparez à nouveau.

Le même contrat s’applique aux tableaux et pipelines. Les paramètres et leur
chemin sont figés dès `job_array_prepare`. `job_pipeline_prepare` valide tous
les scripts et les dépendances avant la première soumission. Seuls les identifiants
Slurm nécessaires aux clauses `--dependency` sont obtenus à l’exécution.

Un appel répété après succès rend les mêmes identifiants avec
`already_submitted=true`. Une tentative en cours, interrompue ou partiellement
échouée ne peut pas être rejouée automatiquement : consulter `list_jobs` avant
de préparer un autre plan. Les étapes déjà soumises d’un pipeline restent actives
et figurent dans `submitted_stages`. Ces protections persistent après redémarrage.

### Migration des anciens noms

Les anciens noms ne sont plus exposés. Relire `tools/list` après mise à jour
et adapter les listes d’outils autorisés dans le client.

| Ancien outil | Remplacement |
|---|---|
| `tool_profile()` / `tool_profile(profile=...)` | `tool_profile_get()` / `tool_profile_set(profile=...)` |
| `job_output(..., lines=...)` / `job_output(..., grep=...)` | `job_log_tail(..., lines=...)` / `job_log_search(..., pattern=...)` |
| `submit_job` | `job_prepare` puis `job_submit` avec `plan_id` |
| `submit_array_job` | `job_array_prepare` puis `job_array_submit` avec `plan_id` |
| `submit_pipeline` | `job_pipeline_prepare` puis `job_pipeline_submit` avec `plan_id` |
| `secret_env_setup` | `secret_env_prepare` (écrit sur ROMEO) |
| `run_cluster_sanity_check` | `cluster_gpu_health_run` (réserve des GPU) |
| `storage_cleanup_helper` | `storage_usage_audit` (lecture seule) |

Pour Hugging Face, créer un venv sur l’architecture de téléchargement, installer
`huggingface_hub` explicitement avec `romeo_pip_install`, puis transmettre ce
chemin à `stage_dataset(..., kind="huggingface", env_path=...)` sur la même
architecture. Le job télécharge un dépôt de type `dataset` et échoue clairement
si le paquet manque ; il ne lance jamais d’installation.

### Plusieurs tableaux dans le même dossier

`job_array_prepare` puis `job_array_submit` permettent de soumettre plusieurs tableaux avec le même nom
et le même `workdir`, même lorsque les précédents attendent encore dans Slurm.
La préparation réserve les noms ; la soumission crée un fichier `parametres-UUID.txt` et un script `NOM-UUID.sbatch`
dans ce dossier. Le script lit les paramètres par leur chemin absolu, et le
fichier de paramètres est placé en lecture seule. La réponse fournit
`parameters_file` et `script_path` ; leurs empreintes SHA-256 sont conservées
dans la [provenance du job](reproducibility.md).

Les scripts des autres soumissions reçoivent aussi un nom unique. Les segments
d'une même chaîne reprenable réutilisent leur propre script. La préparation
écrit le plan local et ne crée aucun fichier distant ; l’UUID des paramètres
est conservé jusqu’à la soumission.
Conservez les paramètres tant que des tâches peuvent encore démarrer ou être
remises en file. Les noms des fichiers de résultats produits par votre commande
restent à choisir pour éviter les collisions entre vos expériences.

### Lire les journaux

`job_log_tail` lit au plus 500 lignes par fichier. `job_log_search` exige un
motif `pattern` compatible `grep -E` ; un motif invalide produit une erreur.
La recherche porte sur les derniers `max_bytes_per_file` octets de chaque
fichier (1 Mio par défaut, 16 Mio au maximum) et rend au plus `max_matches`
correspondances par fichier (60 par défaut, 500 au maximum). Une fenêtre peut
commencer au milieu d’une ligne ; ce n’est pas une recherche exhaustive.
Les deux outils limitent les fichiers par flux (`max_files`, 10 par défaut,
40 au maximum) et le texte renvoyé (`max_chars`, 8 000 par défaut, 40 000 au
maximum). `limits` donne les bornes appliquées, `files_limited` signale un
plafond de fichiers atteint et `truncated` une sortie abrégée.

`job_log_tail.has_stderr_content` indique si au moins un fichier stderr existe
et contient des octets. Un fichier vide ou absent donne `false` ; des espaces
ou sauts de ligne seuls donnent `true`. Ce booléen existe aussi dans `job_log_search` et est indépendant de `pattern`,
du nombre de lignes et du flux demandé, y compris `stream="out"`.

L'affichage ajoute un en-tête seulement aux extraits qui contiennent du texte
non blanc. En mode `auto`, stderr est choisi si un tel extrait subsiste après
filtrage ; sinon stdout est affiché. La présence de stderr ne constitue pas
un verdict d'échec du job : son état et son code de sortie sont dans `job_status`.

## Calcul parallèle

`distributed` choisit la façon de lancer un calcul réparti. **`mpi` est le cas
courant** du cluster : la forme documentée par ROMEO est un simple préfixe
`srun`, sans variable de rendez-vous, avec ou sans GPU.

| Famille | Lanceur | Tâches SLURM | GPU requis |
|---|---|---|---|
| **`mpi`** | `srun <commande>` | libres | non |
| `ddp` | `torchrun`, rendez-vous c10d | 1 par nœud | oui |
| `accelerate` | `accelerate launch` | 1 par nœud | oui |
| `deepspeed`, `srun` | `srun`, rangs issus de SLURM | 1 par GPU | oui |

Sans `srun`, SLURM et OpenMPI ne se coordonnent pas : les rangs ne communiquent
pas et le résultat est faux ou bloqué. Le serveur avertit sur tout job
multi-tâches dont la commande ne passe pas par un lanceur.

### Options réservées à PyTorch

Les quatre dernières familles ajoutent le point de rendez-vous (`MASTER_ADDR`
dérivé du premier nœud alloué, `MASTER_PORT`, `WORLD_SIZE`) et corrigent la
topologie de tâches, car c'est elle qui produit sinon des échecs NCCL tardifs et
illisibles. Elles n'ont aucun sens pour un code Fortran ou C++ : `mpi` suffit.

### Caches Python (`redirect_caches`, désactivé par défaut)

Hugging Face, PyTorch, Triton, pip, uv et matplotlib écrivent sous `~/.cache`,
alors que le home plafonne à 15 Go souples. Activé, ce commutateur redirige
douze variables vers le scratch. Sans objet pour un code compilé, d'où
l'activation explicite.

```bash
export MASTER_ADDR="$(scontrol show hostnames "$SLURM_JOB_NODELIST" | head -n 1)"
export MASTER_PORT=${MASTER_PORT:-29500}
export WORLD_SIZE=$(( SLURM_NNODES * GPUS_PER_NODE ))
```

**Conteneurs** (`container`). La commande est enveloppée dans
`apptainer exec --nv --cleanenv`, avec montage du scratch et de l'espace projet.
Sur `armgpu`, un avertissement rappelle que l'image doit être arm64 : une image
NGC x86 se lance puis échoue au premier appel de noyau. Apptainer 1.4.1 est
disponible via Spack.

## Diagnostic des échecs

`diagnose_job` remplace la séquence habituelle `sacct` → lecture du `.err` →
recherche du code d'erreur. Il combine état, journaux et mesures, puis reconnaît
onze modes d'échec avec, pour chacun, l'extrait de journal qui l'atteste et des
remèdes exprimés dans le vocabulaire des outils du serveur :

| Cause | Signe caractéristique |
|---|---|
| `architecture` | `Illegal instruction` : binaire x86 sur nœud aarch64 |
| `capacite_cuda` | `no kernel image is available` : pas compilé pour sm_90 |
| `memoire_gpu` | `CUDA out of memory` |
| `memoire_vive` | `oom-kill`, ou état `OUT_OF_MEMORY` |
| `memoire_partagee` | `Bus error` : `/dev/shm` plafonné par le cgroup |
| `communication_gpu` | `NCCL WARN`, rendez-vous injoignable |
| `quota` | `Disk quota exceeded` |
| `module_python`, `bibliotheque`, `permission`, `temps`, `noeud` | … |

Sur un dépassement de temps, il cherche en plus les points de reprise présents
dans le répertoire du job.

## Télémétrie en direct

`job_live_metrics` inspecte le matériel d'un job **en cours** sans lire un seul
journal ni attendre la fin, grâce à `srun --overlap` qui superpose une étape à
l'allocation existante : la mesure n'attend donc pas en file et ne consomme pas
d'allocation propre.

Elle ne rend pas que des chiffres, elle les lit : GPU sous 15 % pendant que le
job tourne signale un calcul qui attend ses données ; VRAM au-delà de 90 %
annonce la saturation avant qu'elle ne provoque l'échec ; au-delà de 85 °C, le
ralentissement thermique devient plausible.

`job_stack_trace` prélève la pile des processus via `pstack`, avec repli sur
`gdb` puis `eu-stack`, tous trois présents sur les nœuds. Il ne s'attache pas
de façon interactive : il capture et rend la main, sans interrompre le calcul.
La pile est ensuite interprétée : arrêt dans MPI, collective NCCL bloquée,
attente sur verrou, ou attente d'entrée-sortie.

## Calculs longs sur partition courte

`submit_resilient_job` découpe un calcul en segments enchaînés par
`--dependency=afterany`, ce qui permet d'occuper une partition rapide bien
au-delà de sa limite de temps :

- `#SBATCH --signal=B:SIGUSR1@300` fait prévenir le script avant l'expiration ;
- un piège bash relaie le signal à l'application et dépose un témoin, lui
  laissant le temps d'écrire un point de reprise propre ;
- un marqueur `TERMINE` fait s'effacer les segments restants si le calcul
  finit avant terme.

À ta charge : ton programme doit reprendre depuis `checkpoint_dir` et, au mieux,
traiter `SIGUSR1`.

## Entrées-sorties en mémoire vive

Lire des milliers de petits fichiers depuis GPFS effondre le débit.
`job_prepare(stage_archive=...)` déballe l'archive dans `/dev/shm` au démarrage,
pointe une variable dessus et nettoie par un piège `EXIT`.

Deux limites réelles, mesurées et encodées : `/dev/shm` fait **239 Go** (et non
la taille de la RAM du nœud), et il est **partagé entre les jobs du même nœud**.
Sa consommation étant imputée au cgroup mémoire du job, `--mem` doit couvrir la
taille décompressée.

## Roues aarch64 précompilées

Compiler `deepspeed`, `flash-attn` ou `bitsandbytes` prend de longues minutes,
et recommencer à chaque environnement est du gâchis. `build_wheel` compile une
fois sur un nœud de la bonne architecture et dépose la roue dans
`/scratch_p/$USER/.wheels/aarch64/` ; `romeo_pip_install` l'y retrouve via
`--find-links`, toujours depuis un nœud de calcul.

## Profilage et santé du parc

`profile_job` encapsule le calcul dans **Nsight Systems**, disponible via Spack
(`nvidia-nsight-systems@2024.6.1`). La capture est **fenêtrée** (un délai de
mise en régime puis quelques dizaines de secondes), sans quoi la trace atteint
plusieurs gigaoctets. `profile_report` condense ensuite la sortie `nsys stats`
en quelques constats : part des transferts mémoire face au calcul, noyau
dominant, présence de GEMM suggérant d'activer bf16.

`cluster_gpu_health_run` repère les **nœuds dégradés**, qui ne plantent pas
mais divisent le débit d'un job réparti sans erreur visible : raisons de bridage
décodées depuis le champ de bits de `nvidia-smi`, erreurs mémoire non corrigées,
fréquence anormalement basse sous charge. Il rend une clause `--exclude=` prête
à l'emploi.

Cet outil réserve des GPU avec `srun` : il n’est pas en lecture seule.
Le mode `nccl` est désactivé avant toute connexion ou allocation, car aucun
benchmark NCCL n’est implémenté. `check_type="gpu"` est le seul mode disponible.

## Énergie : un modèle, pas une mesure

ROMEO n'active **aucun greffon de comptabilité énergétique SLURM** :
`AcctGatherEnergyType = (null)`, et `ConsumedEnergyRaw` vaut zéro sur tous les
jobs. `job_energy_footprint` ne peut donc rien mesurer : il modélise, et le dit.

- Sur un job **en cours**, la puissance GPU réelle est relevée par la sonde
  superposée : l'incertitude se réduit fortement.
- Sur un job **terminé**, l'estimation part des ressources allouées et d'un
  facteur de charge, et rend une **fourchette** plutôt qu'un chiffre unique.
- L'intensité carbone par défaut est celle du mix français (56 gCO2e/kWh,
  réglable par `ROMEO_CARBONE_G_KWH`) ; elle varie du simple au triple selon
  l'heure et la saison. Le refroidissement n'est pas compté.

Si le greffon est activé un jour, l'outil bascule automatiquement sur la mesure.

## Hygiène des jobs

**Parallélisme hybride.** Les nœuds sont denses : 192 cœurs en `x64cpu`,
288 en `armgpu`. `OMP_NUM_THREADS` découle de `SLURM_CPUS_PER_TASK`, et
`--cpu-bind=cores` est ajouté dès qu'un rang porte plusieurs fils : sans
liaison, les fils de rangs voisins se disputent les mêmes cœurs et le gain
disparaît. Le serveur avertit si beaucoup de rangs séquentiels laissent la
moitié du nœud inutilisée.

**Répertoire temporaire** (`job_tmpdir`). Les codes de chimie quantique
écrivent des fichiers d'intégrales énormes (`.rwf`, `.scr`) qui saturent un
quota de 20 Go, et laissent des millions de petits fichiers qui alourdissent les
métadonnées GPFS. Le job reçoit un `$TMPDIR` propre, détruit à la sortie
**après rapatriement des résultats** (`.log`, `.chk`, `.out`… configurables).

Bash n'accepte qu'un seul piège `EXIT` : deux `trap … EXIT` s'écrasent
silencieusement. Les préambules empilent donc leurs actions dans une file qu'un
piège unique déroule : le répertoire temporaire et la mise en cache mémoire
cohabitent sans se neutraliser.

**Secrets** (`secret_env_file`). Les valeurs ne transitent **jamais** par le
serveur : `secret_env_prepare` crée un fichier en droits 600 que tu remplis
toi-même sur le cluster, et le script le source au démarrage. Ni le `.sbatch`,
ni le registre SQLite, ni la conversation ne contiennent la valeur.

## Diagnostic système

`diagnose_job` décode le couple `(State, ExitCode)` en plus des journaux. SLURM
note le code sous la forme `code:signal`, si bien qu'un même signal apparaît
sous deux formes selon qui le rapporte ; les deux sont traitées :

| Code | Signification | Piste |
|---|---|---|
| `0:9` ou `137:0` | SIGKILL | tueur de mémoire du noyau, ou annulation |
| `0:11` ou `139:0` | SIGSEGV | pointeur invalide, pile débordée |
| `0:15` ou `143:0` | SIGTERM | fin du temps alloué |
| `127:0` | commande introuvable | environnement non chargé, ou script en CRLF |
| `126:0` | non exécutable | `chmod +x` manquant |

Un binaire tué par SIGKILL n'a pas toujours le temps d'écrire quoi que ce soit :
le code de sortie explique alors l'échec à lui seul.

`sbatch_lint` vérifie un script **avant** l'envoi : fins de ligne Windows qui
font échouer le shebang de façon opaque, `#SBATCH` placés après la première
commande et donc ignorés, `--mem` manquant, chemins inexistants (vérifiés
réellement sur le cluster), variables non définies, secrets en clair.

## Transferts vérifiés

`upload_to_romeo` et `download_from_romeo` calculent une empreinte SHA-256 des
deux côtés et comparent. Un transfert tronqué produit sinon un binaire qui
échoue plus tard de façon opaque.

## Ressources

- `romeo://cheatsheet` : partitions, architectures, quotas, pièges.
- `romeo://limits` : outils absents, outils accessibles via Spack, plafonds.
- `romeo://docs` et `romeo://docs/{+page}` : documentation officielle.
- `romeo://jobs/running` : file personnelle, relue à chaque lecture.
- `romeo://cluster/load` : occupation des nœuds et GPU par architecture.

## Prompts

- `optimize_for_gh200` : adapte un script aux GH200 : roues arm64, `sm_90`,
  96 Gio de VRAM, 288 cœurs Grace, mémoire unifiée.
- `debug_slurm_failure` : enquête guidée sur un job en échec.
- `scale_to_multi_node` : passage d'un entraînement mono-nœud au multi-nœuds.

Le gabarit utilise l'expansion réservée `{+page}` de la RFC 6570 : un simple
`{page}` ne traverse pas les barres obliques, ce qui rendrait inaccessibles les
pages imbriquées comme `ressources/romeo_2025/lancer_un_calcul.md`.

---

## Documentation hors ligne

Le [corpus officiel embarqué](../romeo_mcp/documentation/SOMMAIRE.md) est **versionné
avec le projet et inclus dans les distributions Python**. Il contient 42 pages
officielles et 21 images, ainsi qu'un sommaire, les liens de navigation et
l'attribution URCA. Le [manifeste](../romeo_mcp/documentation/manifest.json) conserve
l'URL source, la date de collecte et les empreintes SHA-256 des fichiers.

Le serveur le trouve relativement à son propre paquet, même lancé depuis un
autre dossier. Aucun fichier dans `Downloads` ni accès réseau n'est nécessaire
pour chercher ou lire la documentation. Le corpus accompagne un clone, un
déplacement des sources ou une installation par wheel. Après déplacement du
projet, recréer le venv si nécessaire et relancer `tools/install_mcp.py` pour
mettre à jour la commande de lancement des clients ; l'installateur n'inscrit
plus de chemin absolu vers le corpus par défaut.

`ROMEO_DOCS_DIR` reste disponible pour un corpus externe choisi explicitement.
Une surcharge invalide est signalée, sans basculer silencieusement sur un autre
corpus. Les liens vers des sites ou documents externes restent des liens Web.

### Recherche et contexte pour le modèle

```python
search_docs("quota home scratch projet", max_results=5,
            page_prefix="ressources/romeo_2025/", max_chars=12000)
search_docs("Memory resource is missing", mode="phrase")
```

- Les mots sont normalisés pour la casse, les accents et les pluriels simples.
  Le classement BM25 tient compte du texte, des titres et de la couverture de la
  requête. Il s'agit d'une recherche lexicale locale, sans modèle d'embeddings.
- Les résultats contiennent des extraits originaux, la hiérarchie des titres,
  les lignes, l'URL source, la date et l'empreinte de la page. Les titres situés
  dans les blocs de code ne découpent pas les sections.
- `max_chars` borne le total des **extraits**, hors métadonnées. Un extrait
  raccourci porte `excerpt_truncated=true` ; `read_args` permet de lire toute la
  section. Les lignes des titres parents permettent de remonter aux prérequis.
- `read_doc(page, start_line=1, end_line=80, max_chars=12000)` lit une plage
  inclusive. Si `truncated=true`, rappeler avec les arguments `next_call`.
  La concaténation des champs `content` restitue exactement le texte demandé,
  même si une ligne est plus longue que le budget. Une empreinte devenue
  différente provoque une erreur explicite, plutôt que de mélanger des versions.
- La recherche a aussi un `next_call` pour parcourir les résultats suivants.
  L'index reste en mémoire et se reconstruit si les fichiers changent.

La recherche ne garantit pas qu'un extrait contienne tous les prérequis d'une
procédure : lire sa section et, si nécessaire, ses sections parentes. Aucune
portion du texte original n'est supprimée du corpus. Les ressources
`romeo://docs` et `romeo://docs/{+page}` servent aussi le texte complet.

Le corpus est un relevé daté. Pour les quotas, partitions et logiciels réellement
disponibles, confronter les règles aux outils qui interrogent le cluster.

### Collecte et vérification

La [source officielle](https://romeo.univ-reims.fr/documentation/) est indiquée
dans chaque page. Pour renouveler le corpus, installer les dépendances de
collecte dans un environnement séparé si le MCP est en cours d'utilisation :

```bash
python -m pip install '.[docs]'
python tools/romeo_doc_scraper.py
python tools/verify_corpus.py
```

Par défaut, la collecte vise `romeo_mcp/documentation` à partir de l'emplacement
du script. `--output` permet de préparer un corpus ailleurs pour inspection.
Vérifier le diff et committer le corpus renouvelé avec le projet.

Le contrôle hors ligne vérifie les empreintes, les liens, les images, l'absence
d'octets NUL et l'accessibilité de toutes les pages depuis le sommaire. La
navigation est reconstruite à partir des barres latérales de toutes les pages
Docusaurus ; les blocs de code conservent leurs retours à la ligne.

Modifier les sources du MCP ne recharge pas les processus déjà lancés : les
nouvelles fonctions sont prises en compte à leur prochain démarrage. Les tests
documentaires démarrent leur propre processus MCP et ne redémarrent pas ceux
des clients en cours d'utilisation.

---

## Le modèle encodé a une date de péremption

Tout ce que ce serveur promet (refuser un job qui resterait en attente, déduire
une partition d'un temps, valider un nombre de nœuds) repose sur un relevé figé.
Un relevé est vrai le jour où on le fait, et rien ne signalait qu'il avait cessé
de l'être. C'est la faiblesse structurelle d'un serveur « correct par
construction » : **sa correction se périme en silence**.

`romeo_selfcheck` interroge SLURM et compare, sur une vingtaine de points :
partitions et limites de temps, nombre de nœuds par partition et par
architecture, cœurs / mémoire / GPU d'un nœud, identifiant GRES, compte, QOS,
plafonds de l'association, et présence des outils déclarés absents.

Il ne corrige rien, car le modèle reste un choix humain, mais chaque écart est
rendu avec sa **portée** : ce qu'il casse concrètement. Une liste de différences
chiffrées sans cette colonne finit toujours par être ignorée.

Deux garde-fous sur le vérificateur lui-même : il refuse de conclure quand la
sonde ne rend rien (un outil qui annonce « tout a disparu » dès qu'il se tait
apprend à ignorer ses propres alertes), et il ne compare pas les valeurs que
`sinfo` marque comme hétérogènes d'un suffixe `+`, sur lesquelles le modèle
retient volontairement la borne basse.

## Les racines sont découvertes, pas supposées

Sur ROMEO, `/home` et `/scratch_p` sont **tous deux des liens symboliques** vers
GPFS. `posixpath` ne résout pas les liens : un chemin physique relevé dans un
script existant (la forme que rend `readlink`, `realpath` ou `pwd`) était
refusé comme « hors périmètre » alors qu'il désigne exactement la racine
autorisée. Coder `/scratch_p/<user>` en dur supposait par ailleurs une
convention que rien ne vérifiait.

La session interroge donc les deux racines au premier contact, retient la forme
documentée comme préférée et ses alias physiques comme équivalents. L'ouverture
reste **portée par utilisateur** : `/gpfs/scratch/<moi>` est accepté,
`/gpfs/scratch/<quelqu'un d'autre>` reste refusé.


## Partis pris de conception

**La préparation et la soumission sont distinctes.** `job_prepare` rend et
conserve le script sbatch exact, les ressources et les avertissements, sans
soumettre. `job_submit` exige l’identifiant de ce plan et `confirm=true`.
Le client peut ainsi distinguer les écritures locales de la soumission sur ROMEO.

**Une session SSH persistante.** Le multiplexage `ControlMaster` d'OpenSSH est
inopérant sous Windows/MSYS : chaque `ssh` coûterait environ 600 ms, prohibitif
pour un serveur dont un modèle enchaîne des dizaines d'appels. Le serveur
maintient un `ssh host bash -l -s` et y pousse les commandes via un protocole à
sentinelles. Mesure : **26 ms par appel au lieu de 600 ms**.

Trois subtilités s'y attachent :

- les tuyaux sont en **binaire**, car en mode texte Windows traduit `\n` en
  `\r\n` sur stdin et le `\r` parasite casse le shell distant ;
- chaque commande tourne dans un **sous-shell**, pour qu'aucun `cd` ni aucune
  variable ne fuie d'un appel à l'autre ;
- `stdin` est détourné vers `/dev/null`, sans quoi un `srun` avale les lignes de
  protocole et corrompt durablement la session.

**Le modèle ne rédige jamais d'en-tête sbatch.** Il décrit une intention ; le
serveur produit `--account`, `--partition`, `--constraint`, `--gpus-per-node`,
`--mem`, les chemins de logs et le chargement d'environnement Spack.

**La simulation doit tenir sans le cluster.** Vérifier un dimensionnement est
le mode le plus utile du serveur, et c'était paradoxalement le plus contraint :
`job_prepare` ouvrait une session SSH pour la seule raison de connaître le
scratch. Une simulation doit pouvoir tourner depuis un portable, et la suite de
tests doit pouvoir l'exercer sans cluster. `ROMEO_SCRATCH` fige les racines ;
à défaut, une simulation hors ligne rend le script en annonçant que ses chemins
sont illustratifs. Une soumission réelle, elle, refuse plutôt que d'inventer un
chemin.

**Deux sessions SSH, pas une.** Le verrou du transport est détenu pendant toute
la durée d'une commande. Avec une seule session, un `build_on_node` de quinze
minutes bloque en tête de file un simple `squeue`. Les commandes dont le délai
dépasse deux minutes basculent donc sur une seconde connexion. Mesure : une
lecture concurrente passe de 8 s d'attente à 0,5 s.

**Les outils vivent dans des modules thématiques.** `server.py` avait atteint
4700 lignes pour 45 outils, seul endroit du dépôt où la qualité du reste ne se
retrouvait pas. Le code est réparti entre `noyau` (serveur, décorateur, appuis
partagés) et cinq modules d'outils : contexte, calcul, exécution, données,
mesure. `server.py` ne fait plus qu'assembler, et réexporte les noms pour que
`romeo_mcp.server.<outil>` continue de fonctionner.

**L'économie de contexte est une contrainte de conception.** Chaque retour est
un résumé compact avec un plafond de taille ; les logs sont tronqués, jamais
déversés.

---
