# Fiches des outils MCP

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › Fiches

Ce dossier contient une fiche Markdown par outil MCP : 71 fiches couvrent les profils `essential`, `full` et `expert`.

Le [catalogue Tools](../Tools.md#outils-exposés) regroupe les outils par usage. Cliquez sur un nom pour lire son rôle, ses paramètres, un exemple JSON, le résultat attendu, les effets et les limites. Chaque fiche propose des liens vers les outils associés et le code correspondant.

Les anciens noms conservés dans la [section de migration](../Tools.md#migration-des-anciens-noms) ne sont plus des outils exposés.

**Sur cette page :** [Choisir une catégorie](#choisir-une-catégorie) · [Lire une fiche](#lire-une-fiche)

## Choisir une catégorie

| Catégorie | Fiches | Exemples |
|---|---:|---|
| [Profil et documentation](../Tools.md#profil-et-documentation) | 4 | [`tool_profile_get`](tool_profile_get.md) · [`tool_profile_set`](tool_profile_set.md) |
| [Cluster et ordonnancement](../Tools.md#cluster-et-ordonnancement) | 8 | [`romeo_status`](romeo_status.md) · [`romeo_software`](romeo_software.md) |
| [Préparation et gestion des jobs](../Tools.md#préparation-et-gestion-des-jobs) | 13 | [`plan_get`](plan_get.md) · [`job_prepare`](job_prepare.md) |
| [Journaux, mesures et profilage](../Tools.md#journaux-mesures-et-profilage) | 11 | [`job_log_tail`](job_log_tail.md) · [`job_log_search`](job_log_search.md) |
| [Services et allocations](../Tools.md#services-et-allocations) | 8 | [`service_prepare`](service_prepare.md) · [`service_start`](service_start.md) |
| [Environnements et paquets Python](../Tools.md#environnements-et-paquets-python) | 6 | [`python_env_prepare`](python_env_prepare.md) · [`python_env_create`](python_env_create.md) |
| [Fichiers, stockage et données](../Tools.md#fichiers-stockage-et-données) | 11 | [`list_dir`](list_dir.md) · [`read_remote_file`](read_remote_file.md) |
| [Scripts Slurm](../Tools.md#scripts-slurm) | 3 | [`sbatch_validate`](sbatch_validate.md) · [`sbatch_check_paths`](sbatch_check_paths.md) |
| [Reproductibilité](../Tools.md#reproductibilité) | 4 | [`job_report_collect`](job_report_collect.md) · [`job_report_from_record`](job_report_from_record.md) |
| [Commandes du profil expert](../Tools.md#commandes-du-profil-expert) | 3 | [`compute_command_prepare`](compute_command_prepare.md) · [`compute_command_run`](compute_command_run.md) |

## Lire une fiche

Utilisez le sommaire de la fiche pour rejoindre directement les paramètres,
l’exemple ou les limites. La rubrique **Voir aussi** mène aux outils associés,
au guide de configuration et au code source. Les liens de retour en bas de
page vous ramènent au catalogue ou à l’index de la documentation.

---

[↑ Haut de page](#fiches-des-outils-mcp) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
