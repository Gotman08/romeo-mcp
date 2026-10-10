# Code du serveur MCP

[Accueil](../README.md) › [Documentation](../docs/README.md) › Code Python

Ce paquet relie un client IA local à ROMEO par OpenSSH et Slurm. Il contient
les outils présentés au modèle, les contrôles des demandes, le transport et
le corpus documentaire. Il s’adresse ici aux personnes qui veulent comprendre
le fonctionnement du serveur ou contribuer à son code.

Pour utiliser le MCP sans modifier Python, commencer par la
[prise en main](../README.md#prise-en-main).

<details>
<summary>Sommaire de cette page</summary>

- [Trajet d’un appel](#trajet-dun-appel)
- [Sections fonctionnelles](#sections-fonctionnelles)
- [Modules de support](#modules-de-support)
- [Où vivent les données ?](#où-vivent-les-données-)
- [Modifier le serveur](#modifier-le-serveur)

</details>

## Trajet d’un appel

![Client IA, MCP local, SSH et nœuds de calcul](../docs/assets/architecture.svg)

1. Le client lance le point d’entrée [cli.py](cli.py), normalement en stdio.
2. [server.py](server.py) importe les modules thématiques, qui enregistrent
   leurs outils grâce au décorateur `outil` de [noyau.py](noyau.py).
3. L’outil valide sa demande et consulte soit le corpus local, soit ROMEO.
4. Pour une préparation, [slurm.py](slurm.py) construit le script et choisit
   les ressources à partir du modèle de cluster et des paramètres fournis.
5. [plans.py](plans.py) fige le script ; la soumission exécute ce contenu via [execution_backend.py](execution_backend.py). Après soumission, [registry.py](registry.py) conserve les références du job
   dans le registre personnel. L’outil rend une réponse structurée au client.

La connexion SSH effectue les opérations distantes ; Slurm attribue les nœuds
qui exécutent le calcul. La préparation par [`job_prepare`](../docs/tools/job_prepare.md) conserve un plan local ;
[`job_submit`](../docs/tools/job_submit.md) en soumet le script exact avec `plan_id` et `confirm: true`.

## Sections fonctionnelles

| Module | Responsabilité | Exemples d’outils |
|---|---|---|
| [outils_contexte.py](outils_contexte.py) | Se situer sur le cluster et lire la documentation | [`romeo_status`](../docs/tools/romeo_status.md), [`romeo_quota`](../docs/tools/romeo_quota.md), [`romeo_software`](../docs/tools/romeo_software.md), [`search_docs`](../docs/tools/search_docs.md), [`read_doc`](../docs/tools/read_doc.md), [`romeo_selfcheck`](../docs/tools/romeo_selfcheck.md) |
| [outils_calcul.py](outils_calcul.py) | Préparer, soumettre et suivre les calculs | [`job_prepare`](../docs/tools/job_prepare.md) / [`job_submit`](../docs/tools/job_submit.md), [`job_array_prepare`](../docs/tools/job_array_prepare.md) / [`job_array_submit`](../docs/tools/job_array_submit.md), [`job_pipeline_prepare`](../docs/tools/job_pipeline_prepare.md) / [`job_pipeline_submit`](../docs/tools/job_pipeline_submit.md), [`job_status`](../docs/tools/job_status.md), [`job_log_tail`](../docs/tools/job_log_tail.md), [`job_efficiency`](../docs/tools/job_efficiency.md) |
| [outils_donnees.py](outils_donnees.py) | Gérer fichiers, transferts et stockage | [`list_dir`](../docs/tools/list_dir.md), [`upload_to_romeo`](../docs/tools/upload_to_romeo.md), [`download_from_romeo`](../docs/tools/download_from_romeo.md), [`dataset_prepare`](../docs/tools/dataset_prepare.md), [`sbatch_validate`](../docs/tools/sbatch_validate.md) |
| [outils_execution.py](outils_execution.py) | Construire des environnements et lancer des services | [`compute_command_prepare`](../docs/tools/compute_command_prepare.md), [`python_wheel_prepare`](../docs/tools/python_wheel_prepare.md), [`python_packages_prepare`](../docs/tools/python_packages_prepare.md), [`service_prepare`](../docs/tools/service_prepare.md) |
| [outils_mesure.py](outils_mesure.py) | Diagnostiquer et observer les calculs | [`diagnose_job`](../docs/tools/diagnose_job.md), [`job_live_metrics`](../docs/tools/job_live_metrics.md), [`job_profile_prepare`](../docs/tools/job_profile_prepare.md), [`job_system_health`](../docs/tools/job_system_health.md) |
| [outils_accompagnement.py](outils_accompagnement.py) | Choisir le catalogue et exporter les preuves d’un job | [`tool_profile_get`](../docs/tools/tool_profile_get.md) / [`tool_profile_set`](../docs/tools/tool_profile_set.md), [`job_report_export`](../docs/tools/job_report_export.md) |

La page [Tools](../docs/Tools.md) donne accès à une fiche par outil, avec ses paramètres, un exemple et ses
limites. Le profil `essential` annonce 22 outils ; `full` annonce les outils métier, `expert` ajoute les exécuteurs génériques au catalogue
complet. Ce choix de découverte est géré par [profiles.py](profiles.py).

## Modules de support

| Domaine | Fichiers à consulter |
|---|---|
| Entrées et version | [Lancement par module](__main__.py), [cli.py](cli.py), [version du paquet](__init__.py) |
| Configuration personnelle et diagnostic | [config.py](config.py), [doctor.py](doctor.py) |
| Mises à jour et lancement des versions | [updates.py](updates.py), [guide utilisateur](../docs/updates.md) |
| Ressources et vérification du modèle | [cluster.py](cluster.py), [verification.py](verification.py) |
| Transport et fichiers | [ssh.py](ssh.py), [files.py](files.py), [remote_paths.py](remote_paths.py), [confined_transfers.py](confined_transfers.py), [sortie.py](sortie.py) |
| Validation locale | [validation.py](validation.py), [guard.py](guard.py) |
| Plans et cycles de vie | [plans.py](plans.py), [services.py](services.py), [service_models.py](service_models.py) |
| Opérations métier | [python_operations.py](python_operations.py), [workload_preparation.py](workload_preparation.py) |
| Adaptateurs Slurm et fichiers atomiques | [execution_backend.py](execution_backend.py), [file_operations.py](file_operations.py) |
| Scripts et dépendances entre jobs | [slurm.py](slurm.py), [templates.py](templates.py), [pipeline.py](pipeline.py) |
| Analyse des échecs et du matériel | [diagnostics.py](diagnostics.py), [hardware.py](hardware.py) |
| Registre, provenance et filtrage | [registry.py](registry.py), [reproducibility.py](reproducibility.py), [privacy.py](privacy.py) |
| Recherche documentaire locale | [docsearch.py](docsearch.py), [corpus et sommaire](documentation/README.md) |

Les caractéristiques encodées du cluster sont des hypothèses datées.
[`romeo_selfcheck`](../docs/tools/romeo_selfcheck.md) permet de les confronter à l’état observé avant de modifier
les règles de dimensionnement.

## Où vivent les données ?

| Emplacement | Contenu |
|---|---|
| Ce paquet | Code, gabarits et documentation officielle embarquée |
| Configuration personnelle hors dépôt | Projet Slurm, alias SSH, QOS et profil d’outils |
| `~/.romeo-mcp/jobs.db` | Registre local, plans exacts, scripts soumis et relevés immuables |
| `~/.romeo-mcp/reports/` | Exports privés de reproductibilité par défaut |
| Répertoire distant du job | Script, journaux, résultats et éventuelle capture `.romeo-provenance/` |

Les chemins personnels et leurs surcharges sont décrits dans le
[guide de configuration](../docs/configuration.md). Les limites des captures
et du filtrage sont décrites dans le [guide de reproductibilité](../docs/reproducibility.md).

## Modifier le serveur

Placer un nouvel outil dans le module correspondant à son rôle, documenter
ses arguments et ses effets, puis vérifier son enregistrement par le protocole
MCP. Un changement de catalogue implique aussi de revoir les profils et
l’inventaire de [smoke_protocol.py](../tests/smoke_protocol.py).

Continuer avec le [guide des tests](../tests/README.md) et les
[règles de contribution](../CONTRIBUTING.md).

---

[↑ Haut de page](#code-du-serveur-mcp) · [Accueil](../README.md) · [Documentation](../docs/README.md) · [Catalogue Tools](../docs/Tools.md)

## Observations et transferts detaches

Le [parcours](../docs/observability.md) explique les garanties et limites. `job_observation.py` separe les observations Slurm du protocole MCP ; `observability.py` porte les caches bornes et compteurs sans contenu. `transfers.py` conserve les plans et statuts ; `transfer_worker.py` supervise les copies sans retenir le processus MCP. Les outils sont assembles depuis `outils_diagnostics.py` et `outils_transferts.py`.
