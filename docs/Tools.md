# Tools

[Accueil](../README.md) › [Documentation](README.md) › Tools

Catalogue des outils MCP du dépôt : cliquez sur le nom d’un outil pour ouvrir sa fiche Markdown.
Chaque fiche explique son rôle, ses paramètres, un exemple d’appel, son résultat, ses effets et ses limites.

<details>
<summary>Sommaire de cette page</summary>

- [Trouver le bon outil](#trouver-le-bon-outil)
- [Outils exposés](#outils-exposés)
  - [Profil et documentation](#profil-et-documentation)
  - [Rapports GitHub du MCP](#rapports-github-du-mcp)
  - [Cluster et ordonnancement](#cluster-et-ordonnancement)
  - [Préparation et gestion des jobs](#préparation-et-gestion-des-jobs)
  - [Journaux, mesures et profilage](#journaux-mesures-et-profilage)
  - [Services et allocations](#services-et-allocations)
  - [Environnements et paquets Python](#environnements-et-paquets-python)
  - [Fichiers, stockage et données](#fichiers-stockage-et-données)
  - [Scripts Slurm](#scripts-slurm)
  - [Reproductibilité](#reproductibilité)
  - [Commandes du profil expert](#commandes-du-profil-expert)
- [Jobs et journaux](#jobs-et-journaux)
  - [Préparer puis soumettre le plan exact](#préparer-puis-soumettre-le-plan-exact)
  - [Migration des anciens noms](#migration-des-anciens-noms)
  - [Cycles de vie et migration des outils composites](#cycles-de-vie-et-migration-des-outils-composites)
  - [Services interactifs](#services-interactifs)
  - [Fichiers et validation](#fichiers-et-validation)
  - [Plusieurs tableaux dans le même dossier](#plusieurs-tableaux-dans-le-même-dossier)
  - [Lire les journaux](#lire-les-journaux)
- [Calcul parallèle](#calcul-parallèle)
  - [Options réservées à PyTorch](#options-réservées-à-pytorch)
  - [Caches Python (redirect_caches, désactivé par défaut)](#caches-python-redirect_caches-désactivé-par-défaut)
- [Diagnostic des échecs](#diagnostic-des-échecs)
- [Télémétrie en direct](#télémétrie-en-direct)
- [Calculs longs sur partition courte](#calculs-longs-sur-partition-courte)
- [Entrées-sorties en mémoire vive](#entrées-sorties-en-mémoire-vive)
- [Roues aarch64 précompilées](#roues-aarch64-précompilées)
- [Profilage et santé du parc](#profilage-et-santé-du-parc)
- [Énergie : un modèle, pas une mesure](#énergie--un-modèle-pas-une-mesure)
- [Hygiène des jobs](#hygiène-des-jobs)
- [Diagnostic système](#diagnostic-système)
- [Transferts vérifiés](#transferts-vérifiés)
- [Ressources](#ressources)
- [Prompts](#prompts)
- [Documentation hors ligne](#documentation-hors-ligne)
  - [Recherche et contexte pour le modèle](#recherche-et-contexte-pour-le-modèle)
  - [Collecte et vérification](#collecte-et-vérification)
- [Le modèle encodé a une date de péremption](#le-modèle-encodé-a-une-date-de-péremption)
- [Les racines sont découvertes, pas supposées](#les-racines-sont-découvertes-pas-supposées)
- [Partis pris de conception](#partis-pris-de-conception)
  - [Organisation des responsabilités](#organisation-des-responsabilités)

</details>

## Trouver le bon outil

| Besoin | Catégorie | Guide |
|---|---|---|
| Profil et documentation | [4 fiches](#profil-et-documentation) | [Configuration des profils](configuration.md#profils-doutils) |
| Rapports GitHub du MCP | [5 fiches](#rapports-github-du-mcp) | [Signalements automatiques autorisés](issue-reports.md) |
| Cluster et ordonnancement | [8 fiches](#cluster-et-ordonnancement) | [État et limites du cluster](#le-modèle-encodé-a-une-date-de-péremption) |
| Préparation et gestion des jobs | [13 fiches](#préparation-et-gestion-des-jobs) | [Préparer puis soumettre](#préparer-puis-soumettre-le-plan-exact) |
| Journaux, mesures et profilage | [11 fiches](#journaux-mesures-et-profilage) | [Lire les journaux](#lire-les-journaux) |
| Services et allocations | [8 fiches](#services-et-allocations) | [Services interactifs](#services-interactifs) |
| Environnements et paquets Python | [6 fiches](#environnements-et-paquets-python) | [Calcul parallèle](#calcul-parallèle) |
| Fichiers, stockage et données | [11 fiches](#fichiers-stockage-et-données) | [Transferts vérifiés](#transferts-vérifiés) |
| Scripts Slurm | [3 fiches](#scripts-slurm) | [Jobs et journaux](#jobs-et-journaux) |
| Reproductibilité | [4 fiches](#reproductibilité) | [Fiches et limites](reproducibility.md) |
| Commandes du profil expert | [3 fiches](#commandes-du-profil-expert) | [Profils et autorisations](configuration.md#profils-doutils) |

Les exemples JSON sont des arguments à transmettre au client MCP, après adaptation des chemins et identifiants. Les commandes shell de ce guide s’exécutent depuis la racine du dépôt.

## Outils exposés

| Profil | Outils annoncés | Usage |
|---|---:|---|
| `essential` | 40 | Documentation, contexte cluster, jobs, reprise, mises à jour, rapports MCP et relevés courants. |
| `full` | 96 | Ensemble des outils métier, y compris tableaux, pipelines, services et profilage. |
| `expert` | 99 | Catalogue complet, avec les trois exécuteurs de commandes arbitraires. |

Le profil par défaut est `full`. [`tool_profile_set`](tools/tool_profile_set.md) change le catalogue de la connexion ; [`tool_profile_get`](tools/tool_profile_get.md) permet de le vérifier.
Les profils règlent la découverte des outils ; les autorisations restent celles du client et de ROMEO. Voir la [configuration des profils](configuration.md#profils-doutils).

Les préparations enregistrent un plan local, valable 24 heures, puis l’action associée exige `plan_id` et `confirm=true`. Les autres actions ont leurs propres effets : consulter la fiche avant l’appel.

### Profil et documentation

| Outil — cliquez pour ouvrir la fiche | À quoi il sert | Profils |
|---|---|---|
| [`tool_profile_get`](tools/tool_profile_get.md) | Consulter le profil actif et les outils annoncés. | `essential`, `full`, `expert` |
| [`tool_profile_set`](tools/tool_profile_set.md) | Changer le profil d’outils de la connexion. | `essential`, `full`, `expert` |
| [`search_docs`](tools/search_docs.md) | Trouver les sections utiles dans la documentation ROMEO. | `essential`, `full`, `expert` |
| [`read_doc`](tools/read_doc.md) | Lire une page ou une plage de lignes du corpus local. | `essential`, `full`, `expert` |

### Mise à jour du MCP

| Outil | Rôle | Profils |
|---|---|---|
| [`mcp_update_check`](tools/mcp_update_check.md) | Détecter une release et présenter les versions exécutée et sélectionnée. | Tous |
| [`mcp_update_policy`](tools/mcp_update_policy.md) | Conserver l'autorisation automatique sans la redemander à chaque version. | Tous |
| [`mcp_update_start`](tools/mcp_update_start.md) | Préparer la release vérifiée dans un environnement séparé. | Tous |
| [`mcp_update_status`](tools/mcp_update_status.md) | Suivre la progression et relire le résultat après reconnexion. | Tous |
| [`mcp_update_rollback`](tools/mcp_update_rollback.md) | Revenir à la version précédente après vérification. | Tous |

Voir le [parcours automatique et les limites de l'activation](updates.md#mise-à-jour-par-le-modèle).

### Rapports GitHub du MCP

| Outil | Rôle | Profils |
|---|---|---|
| [`mcp_issue_policy_get`](tools/mcp_issue_policy_get.md) | Lire la politique de publication et la méthode GitHub configurée. | Tous |
| [`mcp_issue_policy_set`](tools/mcp_issue_policy_set.md) | Enregistrer l'accord automatique initial ou le désactiver. | Tous |
| [`mcp_issue_report`](tools/mcp_issue_report.md) | Filtrer, conserver et éventuellement publier un défaut observé du MCP. | Tous |
| [`mcp_issue_publish`](tools/mcp_issue_publish.md) | Publier un rapport local ou réconcilier un envoi interrompu. | Tous |
| [`mcp_issue_status`](tools/mcp_issue_status.md) | Retrouver les rapports filtrés et les liens GitHub après reconnexion. | Tous |

Voir le [guide des rapports publics et de l'autorisation persistante](issue-reports.md).

### Cluster et ordonnancement

| Outil — cliquez pour ouvrir la fiche | À quoi il sert | Profils |
|---|---|---|
| [`romeo_status`](tools/romeo_status.md) | Consulter l’état du cluster et votre file de jobs. | `essential`, `full`, `expert` |
| [`romeo_software`](tools/romeo_software.md) | Rechercher un logiciel dans le catalogue Spack. | `essential`, `full`, `expert` |
| [`romeo_modules`](tools/romeo_modules.md) | Lister les anciens Environment Modules. | `full`, `expert` |
| [`romeo_quota`](tools/romeo_quota.md) | Lire les quotas réels de stockage. | `essential`, `full`, `expert` |
| [`romeo_selfcheck`](tools/romeo_selfcheck.md) | Comparer le modèle du MCP au cluster actuel. | `full`, `expert` |
| [`cluster_gpu_health_run`](tools/cluster_gpu_health_run.md) | Réserver une courte allocation pour sonder les GPU. | `full`, `expert` |
| [`romeo_fairshare_forecast`](tools/romeo_fairshare_forecast.md) | Estimer l’impact d’une charge sur le fairshare. | `full`, `expert` |
| [`suggest_submission_slot`](tools/suggest_submission_slot.md) | Comparer les partitions pour un calcul envisagé. | `full`, `expert` |

### Préparation et gestion des jobs

| Outil — cliquez pour ouvrir la fiche | À quoi il sert | Profils |
|---|---|---|
| [`plan_get`](tools/plan_get.md) | Relire un plan conservé localement. | `essential`, `full`, `expert` |
| [`job_prepare`](tools/job_prepare.md) | Préparer le script exact d’un job Slurm. | `essential`, `full`, `expert` |
| [`job_submit`](tools/job_submit.md) | Soumettre un job Slurm à partir du plan relu. | `essential`, `full`, `expert` |
| [`job_array_prepare`](tools/job_array_prepare.md) | Préparer un tableau de calculs paramétrés. | `full`, `expert` |
| [`job_array_submit`](tools/job_array_submit.md) | Soumettre un tableau Slurm à partir du plan relu. | `full`, `expert` |
| [`job_pipeline_prepare`](tools/job_pipeline_prepare.md) | Préparer un enchaînement de jobs dépendants. | `full`, `expert` |
| [`job_pipeline_submit`](tools/job_pipeline_submit.md) | Soumettre les étapes d’un pipeline à partir du plan relu. | `full`, `expert` |
| [`job_resilient_prepare`](tools/job_resilient_prepare.md) | Préparer une chaîne de segments reprenables. | `full`, `expert` |
| [`job_resilient_submit`](tools/job_resilient_submit.md) | Soumettre une chaîne de segments reprenables à partir du plan relu. | `full`, `expert` |
| [`job_status`](tools/job_status.md) | Lire l’état d’un job Slurm. | `essential`, `full`, `expert` |
| [`job_link_artifact`](tools/job_link_artifact.md) | Associer localement un artefact existant au dossier d'un job. | `full`, `expert` |
| [`list_jobs`](tools/list_jobs.md) | Retrouver votre file et les jobs enregistrés. | `essential`, `full`, `expert` |
| [`cancel_job`](tools/cancel_job.md) | Demander l’annulation d’un job. | `essential`, `full`, `expert` |
| [`wait_for_job`](tools/wait_for_job.md) | Attendre brièvement la fin d’un job. | `full`, `expert` |

### Journaux, mesures et profilage

| Outil — cliquez pour ouvrir la fiche | À quoi il sert | Profils |
|---|---|---|
| [`job_log_tail`](tools/job_log_tail.md) | Lire la fin des journaux d’un job. | `essential`, `full`, `expert` |
| [`job_log_search`](tools/job_log_search.md) | Rechercher un motif dans les journaux d’un job. | `essential`, `full`, `expert` |
| [`diagnose_job`](tools/diagnose_job.md) | Rassembler un diagnostic de job en échec. | `essential`, `full`, `expert` |
| [`job_efficiency`](tools/job_efficiency.md) | Comparer les ressources réservées et utilisées. | `essential`, `full`, `expert` |
| [`job_live_metrics`](tools/job_live_metrics.md) | Sonder les GPU et les processus d’un job actif. | `full`, `expert` |
| [`job_stack_trace`](tools/job_stack_trace.md) | Prélever des traces de pile d’un job bloqué. | `full`, `expert` |
| [`job_system_health`](tools/job_system_health.md) | Examiner la charge CPU, la mémoire et les attentes d’E/S. | `full`, `expert` |
| [`job_profile_prepare`](tools/job_profile_prepare.md) | Préparer une capture Nsight Systems bornée. | `full`, `expert` |
| [`job_profile_submit`](tools/job_profile_submit.md) | Soumettre un job de profilage GPU à partir du plan relu. | `full`, `expert` |
| [`profile_report`](tools/profile_report.md) | Résumer le rapport d’un job de profilage. | `full`, `expert` |
| [`job_energy_footprint`](tools/job_energy_footprint.md) | Lire l’énergie disponible et calculer une estimation carbone sourcée. | `full`, `expert` |

### Services et allocations

| Outil — cliquez pour ouvrir la fiche | À quoi il sert | Profils |
|---|---|---|
| [`service_prepare`](tools/service_prepare.md) | Préparer un service dans un environnement existant. | `full`, `expert` |
| [`service_start`](tools/service_start.md) | Soumettre un service interactif à partir du plan relu. | `full`, `expert` |
| [`service_status`](tools/service_status.md) | Consulter l’état d’un service. | `full`, `expert` |
| [`service_connection_info`](tools/service_connection_info.md) | Obtenir l’URL et la commande SSH d’un service prêt. | `full`, `expert` |
| [`service_stop`](tools/service_stop.md) | Demander l’arrêt d’un service. | `full`, `expert` |
| [`cluster_allocation_prepare`](tools/cluster_allocation_prepare.md) | Préparer une allocation pour la mise au point. | `full`, `expert` |
| [`cluster_allocation_start`](tools/cluster_allocation_start.md) | Soumettre une allocation de mise au point à partir du plan relu. | `full`, `expert` |
| [`cluster_allocation_connection_info`](tools/cluster_allocation_connection_info.md) | Obtenir une commande de shell pour une allocation active. | `full`, `expert` |

### Environnements et paquets Python

| Outil — cliquez pour ouvrir la fiche | À quoi il sert | Profils |
|---|---|---|
| [`python_env_prepare`](tools/python_env_prepare.md) | Préparer un environnement Python neuf avec une spécification Spack non ambiguë. | `full`, `expert` |
| [`python_env_create`](tools/python_env_create.md) | Soumettre la création d’un venv à partir du plan relu. | `full`, `expert` |
| [`python_packages_prepare`](tools/python_packages_prepare.md) | Préparer l’installation de paquets dans un venv. | `full`, `expert` |
| [`python_packages_install`](tools/python_packages_install.md) | Soumettre l’installation de paquets à partir du plan relu. | `full`, `expert` |
| [`python_wheel_prepare`](tools/python_wheel_prepare.md) | Préparer la construction d’une roue Python. | `full`, `expert` |
| [`python_wheel_build`](tools/python_wheel_build.md) | Soumettre la construction d’une roue Python à partir du plan relu. | `full`, `expert` |

Pour créer un environnement, rechercher Python avec [`romeo_software`](tools/romeo_software.md),
puis fournir dans `spack_packages` une spécification précise (version, compilateur ou empreinte).
Une liste absente ou vide, ainsi que le nom `python` seul, sont refusés dès la préparation.

### Fichiers, stockage et données

| Outil — cliquez pour ouvrir la fiche | À quoi il sert | Profils |
|---|---|---|
| [`list_dir`](tools/list_dir.md) | Lister un répertoire distant. | `essential`, `full`, `expert` |
| [`read_remote_file`](tools/read_remote_file.md) | Lire une tranche de texte sur ROMEO. | `full`, `expert` |
| [`file_create`](tools/file_create.md) | Créer un fichier texte sans écraser une cible. | `full`, `expert` |
| [`file_replace`](tools/file_replace.md) | Remplacer explicitement un fichier texte existant. | `full`, `expert` |
| [`upload_to_romeo`](tools/upload_to_romeo.md) | Envoyer un fichier ou un dossier vers ROMEO. | `essential`, `full`, `expert` |
| [`download_from_romeo`](tools/download_from_romeo.md) | Rapatrier un fichier ou un dossier depuis ROMEO. | `essential`, `full`, `expert` |
| [`storage_usage_audit`](tools/storage_usage_audit.md) | Repérer les principaux consommateurs de stockage. | `full`, `expert` |
| [`audit_orphan_files`](tools/audit_orphan_files.md) | Repérer des fichiers anciens sans job actif associé. | `full`, `expert` |
| [`secret_env_prepare`](tools/secret_env_prepare.md) | Préparer un fichier privé pour les secrets d’un job. | `full`, `expert` |
| [`dataset_prepare`](tools/dataset_prepare.md) | Préparer un téléchargement depuis un nœud de calcul. | `full`, `expert` |
| [`dataset_download`](tools/dataset_download.md) | Soumettre un téléchargement de données à partir du plan relu. | `full`, `expert` |

### Scripts Slurm

| Outil — cliquez pour ouvrir la fiche | À quoi il sert | Profils |
|---|---|---|
| [`sbatch_validate`](tools/sbatch_validate.md) | Analyser le texte d’un script Slurm sans connexion. | `full`, `expert` |
| [`sbatch_check_paths`](tools/sbatch_check_paths.md) | Vérifier les chemins littéraux d’un script sur ROMEO. | `full`, `expert` |
| [`inject_io_staging`](tools/inject_io_staging.md) | Ajouter du staging en RAM à un script existant. | `full`, `expert` |

### Reproductibilité

| Outil — cliquez pour ouvrir la fiche | À quoi il sert | Profils |
|---|---|---|
| [`job_report_collect`](tools/job_report_collect.md) | Conserver un relevé daté de reproductibilité. | `essential`, `full`, `expert` |
| [`job_report_from_record`](tools/job_report_from_record.md) | Créer un relevé à partir du registre local. | `full`, `expert` |
| [`job_report_get`](tools/job_report_get.md) | Relire un relevé de reproductibilité enregistré. | `full`, `expert` |
| [`job_report_export`](tools/job_report_export.md) | Exporter un relevé en JSON et Markdown. | `essential`, `full`, `expert` |

### Commandes du profil expert

| Outil — cliquez pour ouvrir la fiche | À quoi il sert | Profils |
|---|---|---|
| [`compute_command_prepare`](tools/compute_command_prepare.md) | Préparer des commandes arbitraires sur un nœud de calcul. | `expert` |
| [`compute_command_run`](tools/compute_command_run.md) | Soumettre des commandes shell arbitraires à partir du plan relu. | `expert` |
| [`login_command_run`](tools/login_command_run.md) | Exécuter une commande courte sur le login. | `expert` |

## Jobs et journaux

### Préparer puis soumettre le plan exact

[`job_prepare`](tools/job_prepare.md) rend le script, les ressources, les avertissements, un `plan_id`,
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
chemin sont figés dès [`job_array_prepare`](tools/job_array_prepare.md). [`job_pipeline_prepare`](tools/job_pipeline_prepare.md) valide tous
les scripts et les dépendances avant la première soumission. Seuls les identifiants
Slurm nécessaires aux clauses `--dependency` sont obtenus à l’exécution.

Un appel répété après succès rend les mêmes identifiants avec
`already_submitted=true`. Une tentative en cours, interrompue ou partiellement
échouée ne peut pas être rejouée automatiquement : consulter [`list_jobs`](tools/list_jobs.md) avant
de préparer un autre plan. Les étapes déjà soumises d’un pipeline restent actives
et figurent dans `submitted_stages`. Ces protections persistent après redémarrage.

### Migration des anciens noms

Les anciens noms ne sont plus exposés. Relire `tools/list` après mise à jour
et adapter les listes d’outils autorisés dans le client.

| Ancien outil | Remplacement |
|---|---|
| `tool_profile()` / `tool_profile(profile=...)` | `tool_profile_get()` / `tool_profile_set(profile=...)` |
| `job_output(..., lines=...)` / `job_output(..., grep=...)` | `job_log_tail(..., lines=...)` / `job_log_search(..., pattern=...)` |
| `submit_job` | [`job_prepare`](tools/job_prepare.md) puis [`job_submit`](tools/job_submit.md) avec `plan_id` |
| `submit_array_job` | [`job_array_prepare`](tools/job_array_prepare.md) puis [`job_array_submit`](tools/job_array_submit.md) avec `plan_id` |
| `submit_pipeline` | [`job_pipeline_prepare`](tools/job_pipeline_prepare.md) puis [`job_pipeline_submit`](tools/job_pipeline_submit.md) avec `plan_id` |
| `secret_env_setup` | [`secret_env_prepare`](tools/secret_env_prepare.md) (écrit sur ROMEO) |
| `run_cluster_sanity_check` | [`cluster_gpu_health_run`](tools/cluster_gpu_health_run.md) (réserve des GPU) |
| `storage_cleanup_helper` | [`storage_usage_audit`](tools/storage_usage_audit.md) (lecture seule) |

Pour Hugging Face, créer un venv sur l’architecture de téléchargement, installer
`huggingface_hub` avec [`python_packages_prepare`](tools/python_packages_prepare.md) puis [`python_packages_install`](tools/python_packages_install.md), attendre le succès du job, puis transmettre ce
chemin à `dataset_prepare(..., kind="huggingface", env_path=...)` sur la même
architecture, puis appeler `dataset_download(plan_id, confirm=true)`. Le job télécharge un dépôt de type `dataset` et échoue clairement
si le paquet manque ; il ne lance jamais d’installation.

### Cycles de vie et migration des outils composites

Toutes les paires ci-dessous utilisent le même registre local et la même expiration
de 24 heures. La préparation peut lire les racines par SSH ; elle ne soumet rien.
L'action exige seulement `plan_id` et `confirm=true`, sans régénérer le script.
`plan_get(plan_id)` restitue le plan exact et le résultat de sa tentative.

| Ancien outil | Parcours explicite |
|---|---|
| `launch_interactive_service`, `spawn_remote_workspace` | [`service_prepare`](tools/service_prepare.md) → [`service_start`](tools/service_start.md) → [`service_status`](tools/service_status.md) → [`service_connection_info`](tools/service_connection_info.md) ; arrêt par [`service_stop`](tools/service_stop.md) |
| `submit_resilient_job` | [`job_resilient_prepare`](tools/job_resilient_prepare.md) → [`job_resilient_submit`](tools/job_resilient_submit.md) |
| `profile_job` | [`job_profile_prepare`](tools/job_profile_prepare.md) → [`job_profile_submit`](tools/job_profile_submit.md) |
| `stage_dataset` | [`dataset_prepare`](tools/dataset_prepare.md) → [`dataset_download`](tools/dataset_download.md) |
| `build_wheel` | [`python_wheel_prepare`](tools/python_wheel_prepare.md) → [`python_wheel_build`](tools/python_wheel_build.md) |
| `romeo_pip_install` | [`python_packages_prepare`](tools/python_packages_prepare.md) → [`python_packages_install`](tools/python_packages_install.md) |
| `allocate_debug_node` | [`cluster_allocation_prepare`](tools/cluster_allocation_prepare.md) → [`cluster_allocation_start`](tools/cluster_allocation_start.md) |
| `build_on_node` | Outils Python précis ; commandes arbitraires via [`compute_command_prepare`](tools/compute_command_prepare.md) → [`compute_command_run`](tools/compute_command_run.md) dans `expert` |
| `run_login_command` | [`login_command_run`](tools/login_command_run.md), dans `expert` |
| `write_remote_file` | [`file_create`](tools/file_create.md) ou [`file_replace`](tools/file_replace.md) |
| `sbatch_lint` | `sbatch_validate(script)` ou `sbatch_check_paths(script)` |
| `export_job_report` | `job_report_collect(job_id)` → `job_report_export(report_id)` |

### Services interactifs

Exemple de configuration pour [`service_prepare`](tools/service_prepare.md) :

```json
{"config": {"service": "jupyter", "env_path": "/scratch_p/VOTRE_IDENTIFIANT/venv", "port": 8888}, "arch": "armgpu", "gpus_per_node": 1, "time_limit": "2h"}
```

Le venv et le service doivent déjà être installés sur cette architecture. La
configuration est spécifique : TensorBoard exige `logdir`, vLLM exige `model`
et un GPU, Jupyter et MLflow n'acceptent pas ces champs. Les champs sans objet
sont refusés. La préparation ne crée aucun environnement et n'installe rien.

[`service_start`](tools/service_start.md) rend `service_id` et `job_id` après `sbatch`, sans attendre de nœud.
[`service_status`](tools/service_status.md) effectue une lecture Slurm et, si le job tourne, une sonde HTTP
bornée à trois secondes. États : `waiting`, `starting`, `ready`, `failed`,
`stopped`, `unknown`. Une panne de transport ne prouve pas un échec du service.
Le même `service_id` reste utilisable après redémarrage du MCP.

`service_connection_info(service_id, local_port=8888)` fournit la commande SSH
et l'URL seulement quand le service répond. Il n'ouvre aucun tunnel. Jupyter
et vLLM génèrent un jeton dans un fichier privé au démarrage ; TensorBoard et
MLflow restent sans authentification et l'avertissement figure dans leur plan.
[`service_stop`](tools/service_stop.md) demande l'annulation Slurm ; consulter ensuite l'état pour
confirmer l'arrêt. La fin normale du job ferme également le service.

### Fichiers et validation

[`file_create`](tools/file_create.md) refuse une cible existante. [`file_replace`](tools/file_replace.md) exige un fichier
régulier existant et refuse un lien symbolique. Son `expected_sha256` facultatif
empêche d'écraser un contenu qui ne correspond plus à l'empreinte attendue.
La réponse donne la nouvelle empreinte. Les deux outils publient atomiquement
le contenu, exigent un parent existant et acceptent jusqu'à 64 Kio de texte.
Le verrou `.romeo-mcp-files.lock` coordonne ces outils entre processus ; une
écriture concurrente par un autre programme doit respecter le même verrou.

[`sbatch_validate`](tools/sbatch_validate.md) ne reçoit que du texte et n'ouvre aucune connexion.
[`sbatch_check_paths`](tools/sbatch_check_paths.md) vérifie par SSH jusqu'à 20 chemins littéraux dans les
racines autorisées et indique ceux laissés de côté. C'est une analyse lexicale,
sans expansion des variables, des motifs ou du shell. Un chemin de sortie
absent n'est pas nécessairement une erreur de script. Pour analyser un fichier
distant, le lire explicitement avec [`read_remote_file`](tools/read_remote_file.md) puis valider son texte.

### Plusieurs tableaux dans le même dossier

[`job_array_prepare`](tools/job_array_prepare.md) puis [`job_array_submit`](tools/job_array_submit.md) permettent de soumettre plusieurs tableaux avec le même nom
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

[`job_log_tail`](tools/job_log_tail.md) lit au plus 500 lignes par fichier. [`job_log_search`](tools/job_log_search.md) exige un
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
ou sauts de ligne seuls donnent `true`. Ce booléen existe aussi dans [`job_log_search`](tools/job_log_search.md) et est indépendant de `pattern`,
du nombre de lignes et du flux demandé, y compris `stream="out"`.

L'affichage ajoute un en-tête seulement aux extraits qui contiennent du texte
non blanc. En mode `auto`, stderr est choisi si un tel extrait subsiste après
filtrage ; sinon stdout est affiché. La présence de stderr ne constitue pas
un verdict d'échec du job : son état et son code de sortie sont dans [`job_status`](tools/job_status.md).

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

[`diagnose_job`](tools/diagnose_job.md) remplace la séquence habituelle `sacct` → lecture du `.err` →
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

[`job_live_metrics`](tools/job_live_metrics.md) inspecte le matériel d'un job **en cours** sans lire un seul
journal ni attendre la fin, grâce à `srun --overlap` qui superpose une étape à
l'allocation existante : la mesure n'attend donc pas en file et ne consomme pas
d'allocation propre.

Elle ne rend pas que des chiffres, elle les lit : GPU sous 15 % pendant que le
job tourne signale un calcul qui attend ses données ; VRAM au-delà de 90 %
annonce la saturation avant qu'elle ne provoque l'échec ; au-delà de 85 °C, le
ralentissement thermique devient plausible.

[`job_stack_trace`](tools/job_stack_trace.md) prélève la pile des processus via `pstack`, avec repli sur
`gdb` puis `eu-stack`, tous trois présents sur les nœuds. Il ne s'attache pas
de façon interactive : il capture et rend la main, sans interrompre le calcul.
La pile est ensuite interprétée : arrêt dans MPI, collective NCCL bloquée,
attente sur verrou, ou attente d'entrée-sortie.

## Calculs longs sur partition courte

[`job_resilient_prepare`](tools/job_resilient_prepare.md) découpe un calcul en segments enchaînés par
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
et recommencer à chaque environnement est du gâchis. [`python_wheel_prepare`](tools/python_wheel_prepare.md) puis [`python_wheel_build`](tools/python_wheel_build.md) compilent une
fois sur un nœud de la bonne architecture et dépose la roue dans
`/scratch_p/$USER/.wheels/aarch64/` ; [`python_packages_prepare`](tools/python_packages_prepare.md) puis [`python_packages_install`](tools/python_packages_install.md) l'y retrouvent via
`--find-links`, toujours depuis un nœud de calcul.

## Profilage et santé du parc

[`job_profile_prepare`](tools/job_profile_prepare.md) prépare le script ; [`job_profile_submit`](tools/job_profile_submit.md) lance le job. Le script encapsule le calcul dans **Nsight Systems**, disponible via Spack
(`nvidia-nsight-systems@2024.6.1`). La capture est **fenêtrée** (un délai de
mise en régime puis quelques dizaines de secondes), sans quoi la trace atteint
plusieurs gigaoctets. [`profile_report`](tools/profile_report.md) condense ensuite la sortie `nsys stats`
en quelques constats : part des transferts mémoire face au calcul, noyau
dominant, présence de GEMM suggérant d'activer bf16.

[`cluster_gpu_health_run`](tools/cluster_gpu_health_run.md) repère les **nœuds dégradés**, qui ne plantent pas
mais divisent le débit d'un job réparti sans erreur visible : raisons de bridage
décodées depuis le champ de bits de `nvidia-smi`, erreurs mémoire non corrigées,
fréquence anormalement basse sous charge. Il rend une clause `--exclude=` prête
à l'emploi.

Cet outil réserve des GPU avec `srun` : il n’est pas en lecture seule.
Le mode `nccl` est désactivé avant toute connexion ou allocation, car aucun
benchmark NCCL n’est implémenté. `check_type="gpu"` est le seul mode disponible.

## Énergie et carbone

[`job_energy_footprint`](tools/job_energy_footprint.md) lit les compteurs Slurm.
Une énergie absente ou nulle reste inconnue, et une allocation exclusive vérifiée
est nécessaire pour attribuer un compteur positif au job.

Le modèle est facultatif (`estimate_if_unavailable=true`) et reste séparé de la
mesure. Le facteur fixe de 56 gCO2e/kWh a été retiré : RTE fournit un facteur daté
sur la période du calcul, ou l'appelant fournit un facteur avec sa référence.
L'émission reste estimée, avec son périmètre et ses limites, sans la présenter
comme un capteur de CO2. Voir [Mesures et carbone](energy.md).

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
serveur : [`secret_env_prepare`](tools/secret_env_prepare.md) crée un fichier en droits 600 que tu remplis
toi-même sur le cluster, et le script le source au démarrage. Ni le `.sbatch`,
ni le registre SQLite, ni la conversation ne contiennent la valeur.

## Diagnostic système

[`diagnose_job`](tools/diagnose_job.md) décode le couple `(State, ExitCode)` en plus des journaux. SLURM
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

[`sbatch_validate`](tools/sbatch_validate.md) vérifie un script **avant** l'envoi : fins de ligne Windows qui
font échouer le shebang de façon opaque, `#SBATCH` placés après la première
commande et donc ignorés, `--mem` manquant, chemins inexistants (vérifiés
réellement sur le cluster), variables non définies, secrets en clair.

## Transferts vérifiés

[`upload_to_romeo`](tools/upload_to_romeo.md) et [`download_from_romeo`](tools/download_from_romeo.md) calculent une empreinte SHA-256 des
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

[`romeo_selfcheck`](tools/romeo_selfcheck.md) interroge SLURM et compare, sur une vingtaine de points :
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

**La préparation et la soumission sont distinctes.** [`job_prepare`](tools/job_prepare.md) rend et
conserve le script sbatch exact, les ressources et les avertissements, sans
soumettre. [`job_submit`](tools/job_submit.md) exige l’identifiant de ce plan et `confirm=true`.
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
[`job_prepare`](tools/job_prepare.md) ouvrait une session SSH pour la seule raison de connaître le
scratch. Une simulation doit pouvoir tourner depuis un portable, et la suite de
tests doit pouvoir l'exercer sans cluster. `ROMEO_SCRATCH` fige les racines ;
à défaut, une simulation hors ligne rend le script en annonçant que ses chemins
sont illustratifs. Une soumission réelle, elle, refuse plutôt que d'inventer un
chemin.

**Deux sessions SSH, pas une.** Le verrou du transport est détenu pendant toute
la durée d'une commande. Avec une seule session, une sonde synchrone de plusieurs
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

### Organisation des responsabilités

- `outils_*.py` : interface MCP, schémas et annotations d'effets.
- `plans.py`, `services.py`, `python_operations.py`, `workload_preparation.py` et `reproducibility.py` : règles métier et composition des opérations.
- `execution_backend.py`, `ssh.py`, `registry.py`, `file_operations.py` : adaptateurs Slurm, transport SSH, SQLite et publication des fichiers.
- `slurm.py`, `templates.py`, `validation.py` : génération et validation locale testables sans connexion.

Les opérations existantes de diagnostic et les transferts avec vérification
d'intégrité conservent leur intention unique.

---

[↑ Haut de page](#tools) · [Accueil](../README.md) · [Documentation](README.md)

## Diagnostics et transferts detaches

[Parcours, mesures et limites](observability.md)

| Outil | Fonction |
|---|---|
| [`mcp_diagnostics`](tools/mcp_diagnostics.md) | Lecture locale des compteurs ; aucune connexion SSH ouverte. |
| [`romeo_capabilities`](tools/romeo_capabilities.md) | Lecture locale de la configuration et du profil ; la disponibilite du cluster reste a observer. |
| [`job_observation_get`](tools/job_observation_get.md) | Dernier etat conserve, avec son age. Ne certifie pas la cible ou l etat actuel. |
| [`transfer_prepare`](tools/transfer_prepare.md) | Ecrit uniquement un plan local. Verifie les chemins avec les racines SSH configurees. |
| [`transfer_start`](tools/transfer_start.md) | Lance la copie apres confirmation, une seule fois par plan. |
| [`transfer_status`](tools/transfer_status.md) | Relit les traces locales, sans attendre ni relancer une copie. |
| [`transfer_cancel`](tools/transfer_cancel.md) | Demande l annulation ; seul le worker peut en confirmer l observation. |

## Checkpoints, reprise et environnement parallele

[Guide du contrat generique](checkpoints.md)

| Outil | Effet |
|---|---|
| [`job_resume_prepare`](tools/job_resume_prepare.md) | Enregistre un plan local depuis un job termine. Lit les preuves et l etat Slurm ; aucune ecriture ni soumission sur ROMEO. |
| [`job_resume_submit`](tools/job_resume_submit.md) | Ecrit les fichiers scelles et appelle sbatch apres confirm=true, une seule fois par plan. |
| [`job_resume_status`](tools/job_resume_status.md) | Lecture des preuves distantes et de Slurm ; conserve une observation locale datee. |
| [`job_checkpoint_request`](tools/job_checkpoint_request.md) | Envoie SIGUSR1 au batch apres observation RUNNING. Ne certifie aucune sauvegarde. |
| [`checkpoint_inspect`](tools/checkpoint_inspect.md) | Lecture bornee des manifestes ; aucun hachage des gros fichiers ni soumission. |
| [`checkpoint_protect_prepare`](tools/checkpoint_protect_prepare.md) | Enregistre un plan local pour un petit job de verification/copie. Aucune copie pendant la preparation. |
| [`checkpoint_protect_submit`](tools/checkpoint_protect_submit.md) | Depose le plan exact et appelle sbatch apres confirm=true. |
| [`checkpoint_export_prepare`](tools/checkpoint_export_prepare.md) | Prepare un transfert local scelle, sans copier de fichier. |
| [`checkpoint_export_status`](tools/checkpoint_export_status.md) | Lit le transfert et, apres copie, hache les fichiers sur la machine du client. Conserve une preuve locale datee. |
| [`job_environment_status`](tools/job_environment_status.md) | Lit le releve MPI produit dans l allocation et conserve une observation locale datee. |
