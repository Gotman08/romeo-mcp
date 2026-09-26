# Utiliser ROMEO 2025

[Corpus ROMEO](../../README.md) › [Ressources](../README.md) › ROMEO 2025

Ce parcours ordonne les procédures officielles utiles à un calcul : se
connecter, préparer ses fichiers et logiciels, soumettre, puis examiner le
résultat. La [présentation de ROMEO 2025](../romeo_2025.md) donne le contexte
de cette ressource.

## Avant le premier calcul

Disposer d’un [compte autorisé](../../creation_compte.md), d’un accès SSH et
d’un projet Slurm. Avec le MCP, la configuration personnelle et
`doctor --live` permettent de contrôler les accès depuis le même poste qui
lance le client IA.

## Parcours conseillé

| Étape | Procédure officielle | À conserver pour la suite |
|---|---|---|
| 1. Se connecter | [Connexion à ROMEO 2025](se_connecter.md) | Alias et environnement SSH utilisés |
| 2. Préparer les fichiers | [Transfert de données](transferer_données.md), [espaces de stockage](espaces_de_stockage.md) | Répertoire de travail et emplacement des entrées |
| 3. Préparer les logiciels | [Chargement](charger_ses_logiciels.md), [installation](installer_un_logiciel.md), [catalogues](Logiciels/README.md) | Architecture, paquets et versions choisis |
| 4. Décrire le job | [Script de soumission](ecrire_un_fichier_de_soumission.md) | Commande, durée, CPU, mémoire et éventuels GPU |
| 5. Soumettre et suivre | [Lancer un calcul](lancer_un_calcul.md), [commandes utiles](commandes_utiles.md) | Identifiant du job, script et journaux |

Dans le MCP, préparer d’abord `submit_job` avec `confirm: false`, lire les
avertissements, puis autoriser la soumission. Les informations de ces étapes
servent ensuite au suivi, au diagnostic et à la fiche de reproductibilité.

## Selon le type de travail

| Besoin | Lecture |
|---|---|
| Programme Python | [Utiliser Python](utiliser_python.md) |
| Calcul MPI | [Utiliser OpenMPI](utiliser_openmpi.md) |
| Calcul GPU | [Utiliser les GPU](utiliser_des_gpu.md) et [catalogues par architecture](Logiciels/README.md) |
| Notebook | [Utiliser JupyterLab](7.1.utiliser_jupyterlab.md) |
| Interface de visualisation | [Session de visualisation](utiliser_une_session_de_visu.md) |
| Approfondissement | [Pour aller plus loin](plus_loin.md) |

## Portée des informations

Les pages sont celles de la collecte datée dans le [manifeste](../../manifest.json).
Les quotas, autorisations et disponibilités du moment se vérifient sur le
cluster. Une commande doit rester associée à l’architecture et à la procédure
qui l’expliquent.

[Retour aux ressources](../README.md) · [Sommaire officiel](../../SOMMAIRE.md)

*Guide de navigation du projet MCP. Les procédures liées sont attribuées à ROMEO / URCA.*
