# Code du serveur MCP

[Accueil](../README.md) › [Documentation](../docs/README.md) › Code Python

Ce paquet relie un client IA local à ROMEO par OpenSSH et Slurm. Il contient
les outils présentés au modèle, les contrôles des demandes, le transport et
le corpus documentaire. Il s’adresse ici aux personnes qui veulent comprendre
le fonctionnement du serveur ou contribuer à son code.

Pour utiliser le MCP sans modifier Python, commencer par la
[prise en main](../README.md#prise-en-main).

## Trajet d’un appel

![Client IA, MCP local, SSH et nœuds de calcul](../docs/assets/architecture.svg)

1. Le client lance le point d’entrée [cli.py](cli.py), normalement en stdio.
2. [server.py](server.py) importe les modules thématiques, qui enregistrent
   leurs outils grâce au décorateur `outil` de [noyau.py](noyau.py).
3. L’outil valide sa demande et consulte soit le corpus local, soit ROMEO.
4. Pour une soumission, [slurm.py](slurm.py) construit le script et choisit
   les ressources à partir du modèle de cluster et des paramètres fournis.
5. Après soumission, [registry.py](registry.py) conserve les références du job
   dans le registre personnel. L’outil rend une réponse structurée au client.

La connexion SSH effectue les opérations distantes ; Slurm attribue les nœuds
qui exécutent le calcul. La préparation par `job_prepare` conserve un plan local ;
`job_submit` en soumet le script exact avec `plan_id` et `confirm: true`.

## Sections fonctionnelles

| Module | Responsabilité | Exemples d’outils |
|---|---|---|
| [outils_contexte.py](outils_contexte.py) | Se situer sur le cluster et lire la documentation | `romeo_status`, `romeo_quota`, `romeo_software`, `search_docs`, `read_doc`, `romeo_selfcheck` |
| [outils_calcul.py](outils_calcul.py) | Préparer, soumettre et suivre les calculs | `job_prepare` / `job_submit`, `job_array_prepare` / `job_array_submit`, `job_pipeline_prepare` / `job_pipeline_submit`, `job_status`, `job_log_tail`, `job_efficiency` |
| [outils_donnees.py](outils_donnees.py) | Gérer fichiers, transferts et stockage | `list_dir`, `upload_to_romeo`, `download_from_romeo`, `stage_dataset`, `sbatch_lint` |
| [outils_execution.py](outils_execution.py) | Construire des environnements et lancer des services | `build_on_node`, `build_wheel`, `romeo_pip_install`, `launch_interactive_service` |
| [outils_mesure.py](outils_mesure.py) | Diagnostiquer et observer les calculs | `diagnose_job`, `job_live_metrics`, `profile_job`, `job_system_health` |
| [outils_accompagnement.py](outils_accompagnement.py) | Choisir le catalogue et exporter les preuves d’un job | `tool_profile_get` / `tool_profile_set`, `export_job_report` |

La [référence utilisateur](../docs/reference.md) détaille les fonctions et leurs
limites. Le profil `essential` annonce 20 outils ; `full` annonce le catalogue
complet. Ce choix de découverte est géré par [profiles.py](profiles.py).

## Modules de support

| Domaine | Fichiers à consulter |
|---|---|
| Entrées et version | [Lancement par module](__main__.py), [cli.py](cli.py), [version du paquet](__init__.py) |
| Configuration personnelle et diagnostic | [config.py](config.py), [doctor.py](doctor.py) |
| Mises à jour et lancement des versions | [updates.py](updates.py), [guide utilisateur](../docs/updates.md) |
| Ressources et vérification du modèle | [cluster.py](cluster.py), [verification.py](verification.py) |
| Transport et fichiers | [ssh.py](ssh.py), [files.py](files.py), [sortie.py](sortie.py) |
| Validation des commandes et chemins | [guard.py](guard.py) |
| Scripts et dépendances entre jobs | [slurm.py](slurm.py), [templates.py](templates.py), [pipeline.py](pipeline.py) |
| Analyse des échecs et du matériel | [diagnostics.py](diagnostics.py), [hardware.py](hardware.py) |
| Registre, provenance et filtrage | [registry.py](registry.py), [reproducibility.py](reproducibility.py), [privacy.py](privacy.py) |
| Recherche documentaire locale | [docsearch.py](docsearch.py), [corpus et sommaire](documentation/README.md) |

Les caractéristiques encodées du cluster sont des hypothèses datées.
`romeo_selfcheck` permet de les confronter à l’état observé avant de modifier
les règles de dimensionnement.

## Où vivent les données ?

| Emplacement | Contenu |
|---|---|
| Ce paquet | Code, gabarits et documentation officielle embarquée |
| Configuration personnelle hors dépôt | Projet Slurm, alias SSH, QOS et profil d’outils |
| `~/.romeo-mcp/jobs.db` | Registre local et scripts des jobs soumis |
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
