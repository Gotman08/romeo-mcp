# Documentation du MCP ROMEO

[Accueil du projet](../README.md) › Documentation

Ce dossier explique comment utiliser le MCP et comprendre ses résultats.
Les procédures du centre de calcul sont conservées dans le
[corpus officiel ROMEO](../romeo_mcp/documentation/README.md), avec leurs sources
et leur date de collecte.

<details>
<summary>Sommaire de cette page</summary>

- [Démarrer](#démarrer)
- [Utiliser les outils](#utiliser-les-outils)
- [Diagnostiquer et conserver les résultats](#diagnostiquer-et-conserver-les-résultats)
- [Consulter les procédures ROMEO](#consulter-les-procédures-romeo)
- [Mettre à jour et contribuer](#mettre-à-jour-et-contribuer)
- [Les guides](#les-guides)
- [Lire un résultat dans son contexte](#lire-un-résultat-dans-son-contexte)
- [Repères pour les contributeurs](#repères-pour-les-contributeurs)

</details>

## Démarrer

| Vous souhaitez… | Point de départ | Étape suivante |
|---|---|---|
| Installer le MCP pour un cours ou un projet | [Prise en main](../README.md#prise-en-main) | [Configuration et diagnostic](configuration.md) |
| Connecter votre client IA | [Installation des clients](../tools/README.md#enregistrer-le-mcp-dans-un-client) | [Autres clients stdio](configuration.md#autres-clients-stdio) |
| Lancer votre premier calcul | [Premier essai](../README.md#4-faire-un-premier-essai) | [Préparer](tools/job_prepare.md), [soumettre](tools/job_submit.md), [suivre](tools/job_status.md) |
| Présenter moins d’outils à l’IA | [Profils d’outils](configuration.md#profils-doutils) | [Catalogue complet](Tools.md#outils-exposés) |
| Déplacer votre installation ou utiliser WSL | [Déplacement](configuration.md#déplacer-ou-mettre-à-jour-linstallation) | [WSL](configuration.md#wsl) |

## Utiliser les outils

Le [catalogue Tools](Tools.md#outils-exposés) rassemble les **71 fiches** par
catégorie. Chaque fiche contient une explication, les paramètres, un exemple
JSON, les résultats attendus et des liens vers les outils associés.

| Votre besoin | Guide | Fiches à ouvrir |
|---|---|---|
| Préparer et suivre un job | [Jobs et journaux](Tools.md#jobs-et-journaux) | [Préparer](tools/job_prepare.md) · [Soumettre](tools/job_submit.md) · [État](tools/job_status.md) · [Retrouver mes jobs](tools/list_jobs.md) |
| Lancer plusieurs expériences | [Tableaux et pipelines](Tools.md#préparer-puis-soumettre-le-plan-exact) | [Tableau de paramètres](tools/job_array_prepare.md) · [Étapes dépendantes](tools/job_pipeline_prepare.md) · [Calcul reprenable](tools/job_resilient_prepare.md) |
| Choisir les logiciels et l’architecture | [Calcul parallèle](Tools.md#calcul-parallèle) | [Catalogue Spack](tools/romeo_software.md) · [Environnement Python](tools/python_env_prepare.md) · [Paquets Python](tools/python_packages_prepare.md) |
| Manipuler les fichiers | [Fichiers et validation](Tools.md#fichiers-et-validation) | [Lister](tools/list_dir.md) · [Lire](tools/read_remote_file.md) · [Créer](tools/file_create.md) · [Remplacer](tools/file_replace.md) |
| Transférer les données | [Transferts vérifiés](Tools.md#transferts-vérifiés) | [Envoyer](tools/upload_to_romeo.md) · [Récupérer](tools/download_from_romeo.md) · [Vérifier les quotas](tools/romeo_quota.md) |
| Ouvrir un service interactif | [Services](Tools.md#services-interactifs) | [Préparer](tools/service_prepare.md) · [Démarrer](tools/service_start.md) · [Se connecter](tools/service_connection_info.md) · [Arrêter](tools/service_stop.md) |
| Lire la documentation avec l’IA | [Recherche locale](Tools.md#recherche-et-contexte-pour-le-modèle) | [Chercher une section](tools/search_docs.md) · [Lire la page](tools/read_doc.md) |

## Diagnostiquer et conserver les résultats

| Vous souhaitez… | Point de départ | Étape suivante |
|---|---|---|
| Comprendre un refus ou un échec | [Diagnostic des accès](configuration.md#diagnostic-en-lecture-seule) | [Diagnostic des jobs](Tools.md#diagnostic-des-échecs) |
| Lire les journaux d’un job | [Lecture ciblée](Tools.md#lire-les-journaux) | [Fin du journal](tools/job_log_tail.md) · [Recherche dans les logs](tools/job_log_search.md) |
| Examiner les performances | [Diagnostic système](Tools.md#diagnostic-système) | [Efficacité](tools/job_efficiency.md) · [Mesures en direct](tools/job_live_metrics.md) · [Rapport de profilage](tools/profile_report.md) |
| Conserver les conditions d’une expérience | [Fiches de reproductibilité](reproducibility.md) | [Mesures et limites](reproducibility.md#ce-qui-est-réellement-mesuré) |
| Exporter un relevé précis | [Collecter puis exporter](reproducibility.md#collecter-puis-exporter-après-le-calcul) | [Collecte](tools/job_report_collect.md) · [Export privé](tools/job_report_export.md) |

## Consulter les procédures ROMEO

Le [guide du corpus officiel](../romeo_mcp/documentation/README.md) présente
la provenance et les limites de cette copie. Le
[sommaire complet](../romeo_mcp/documentation/SOMMAIRE.md) donne accès aux
42 pages officielles.

| Sujet | Pages à consulter |
|---|---|
| Compte et accès | [Création du compte](../romeo_mcp/documentation/creation_compte.md) · [Clés SSH](../romeo_mcp/documentation/ressources/connexion_ssh.md) · [Connexion ROMEO 2025](../romeo_mcp/documentation/ressources/romeo_2025/se_connecter.md) |
| Parcours du premier calcul | [Guide ROMEO 2025](../romeo_mcp/documentation/ressources/romeo_2025/README.md) · [Écrire un script Slurm](../romeo_mcp/documentation/ressources/romeo_2025/ecrire_un_fichier_de_soumission.md) · [Lancer un calcul](../romeo_mcp/documentation/ressources/romeo_2025/lancer_un_calcul.md) |
| Logiciels, Python, MPI et GPU | [Catalogues par architecture](../romeo_mcp/documentation/ressources/romeo_2025/Logiciels/README.md) · [Python](../romeo_mcp/documentation/ressources/romeo_2025/utiliser_python.md) · [OpenMPI](../romeo_mcp/documentation/ressources/romeo_2025/utiliser_openmpi.md) · [GPU](../romeo_mcp/documentation/ressources/romeo_2025/utiliser_des_gpu.md) |
| Données et stockage | [Espaces de stockage](../romeo_mcp/documentation/ressources/romeo_2025/espaces_de_stockage.md) · [Transfert de données](../romeo_mcp/documentation/ressources/romeo_2025/transferer_données.md) |
| Interfaces interactives | [JupyterLab](../romeo_mcp/documentation/ressources/romeo_2025/7.1.utiliser_jupyterlab.md) · [Visualisation](../romeo_mcp/documentation/ressources/romeo_2025/utiliser_une_session_de_visu.md) |
| Services et assistance | [Services ROMEO](../romeo_mcp/documentation/services/README.md) · [Assistance](../romeo_mcp/documentation/services/assistance.md) · [Accompagnement scientifique](../romeo_mcp/documentation/services/accompagnementScientifiqueCode.md) · [Oratio](../romeo_mcp/documentation/services/Oratio/README.md) |
| Autres ressources et archives | [Ressources](../romeo_mcp/documentation/ressources/README.md) · [Juliet](../romeo_mcp/documentation/ressources/juliet/README.md) · [QLM](../romeo_mcp/documentation/ressources/qlm/README.md) · [Historique](../romeo_mcp/documentation/historique/README.md) · [Archives ROMEO 2018](../romeo_mcp/documentation/ressources/archives/README.md) |
| Règles et sécurité | [Charte ROMEO](../romeo_mcp/documentation/2.5.charte.md) · [Bonnes pratiques de cybersécurité](../romeo_mcp/documentation/bonnes_pratiques_cybersecurite.md) |

## Mettre à jour et contribuer

| Vous souhaitez… | Point de départ | Étape suivante |
|---|---|---|
| Installer une nouvelle version | [Mises à jour GitHub](updates.md) | [Historique des versions](../CHANGELOG.md) |
| Revenir à une version précédente | [Retour arrière](updates.md#revenir-à-la-version-précédente) | [Versions conservées](updates.md#où-sont-conservées-les-versions-) |
| Contribuer au projet | [Architecture du code](../romeo_mcp/README.md) | [Tests](../tests/README.md) et [contribution](../CONTRIBUTING.md) |

## Les guides

- [Configuration](configuration.md) : accès personnels, priorités des réglages,
  profils `essential`, `full` et `expert`, clients stdio, `doctor --live`, déplacement et WSL.
- [Tools](Tools.md) : catalogue cliquable de 71 outils MCP, fiches par outil, MPI et GPU, logiciels,
  stockage, diagnostics, mesures et limites de conception.
- [Reproductibilité](reproducibility.md) : capture des informations d’un job,
  empreintes des entrées, export privé, dates d’observation et données manquantes.
- [Visuels](assets/README.md) : schéma de fonctionnement, bannière et attributions.
- [Mises à jour](updates.md) : versions stables, confirmation, activation et retour arrière.

## Lire un résultat dans son contexte

La simulation d’un job produit un script et des avertissements. La soumission
donne un identifiant Slurm. L’état `COMPLETED` indique la fin du processus ;
la validité scientifique reste à vérifier dans les résultats de l’expérience.

Pour interpréter une fiche ou un diagnostic, conserver ensemble la source,
la date, les paramètres et les limites indiquées. Le corpus embarqué est une
copie datée ; les accès et quotas effectifs se vérifient avec les outils distants.
Les extraits de recherche conduisent aux sections complètes via [`read_doc`](tools/read_doc.md).

## Repères pour les contributeurs

| Section | Ce qu’elle documente |
|---|---|
| [Code Python](../romeo_mcp/README.md) | Responsabilités des modules et trajet d’un appel |
| [Utilitaires](../tools/README.md) | Installation des clients, contrôle de confidentialité et entretien du corpus |
| [Tests](../tests/README.md) | Suites hors ligne et essais sur ROMEO |
| [GitHub](../.github/CONFIGURATION.md) | Vérifications automatiques du dépôt |
| [Hooks Git](../.githooks/README.md) | Contrôles locaux avant commit et push |

Pour signaler une vulnérabilité, suivre le [guide de sécurité](../SECURITY.md).
Pour les règles de redistribution, consulter la [licence](../LICENSE) et
les [mentions des contenus tiers](../THIRD_PARTY_NOTICES.md).

---

[↑ Haut de page](#documentation-du-mcp-romeo) · [Accueil](../README.md) · [Catalogue Tools](Tools.md)
