<div align="center">

# ROMEO MCP

**Du dialogue avec votre IA au calcul scientifique sur ROMEO.**

Un serveur MCP local pour préparer, soumettre, suivre et comprendre vos calculs Slurm.

[Prise en main](#prise-en-main) · [Fonctionnement](#comment-ça-fonctionne) · [Référence](docs/reference.md) · [Documentation ROMEO](romeo_mcp/documentation/SOMMAIRE.md)

[![Vérifications](https://github.com/Gotman08/romeo-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/Gotman08/romeo-mcp/actions/workflows/ci.yml)
![Python 3.11 et plus](https://img.shields.io/badge/Python-3.11%2B-3776AB)
![Transport stdio](https://img.shields.io/badge/MCP-stdio-1D6D70)
[![Licence MIT](https://img.shields.io/badge/code-MIT-D4A95E)](LICENSE)

<a href="https://romeo.univ-reims.fr/18_actualites.html/149/Romeo_le_cinquieme_supercalculateur_le_plus_eco-efficace_du_monde."><img src="docs/assets/romeo-banner.png" alt="Illustration du supercalculateur ROMEO dans l’article officiel de novembre 2013" width="960"></a>

<sub>Source : Centre de Calcul Régional ROMEO / URCA, article du 21 novembre 2013.</sub>

</div>

## Pour qui ?

Étudiants, enseignants et chercheurs disposant d’un accès **déjà autorisé** à ROMEO : simulation numérique, chimie, bio-informatique, statistiques, calcul MPI ou apprentissage automatique.

Décrivez votre besoin à votre assistant IA. Le MCP lui fournit les outils pour consulter la documentation, construire un script Slurm, vérifier les ressources demandées et suivre le résultat. Il utilise votre connexion SSH et les droits de votre compte.

**Projet communautaire indépendant.** Ce dépôt n’est pas un service officiel de l’Université de Reims Champagne-Ardenne. L’accès au calculateur et ses règles restent ceux de [ROMEO](https://romeo.univ-reims.fr/).

| Votre besoin | Ce que fournit le MCP |
|---|---|
| Préparer un calcul | Script Slurm, choix de partition, contrôles CPU, RAM et architecture |
| Utiliser les GPU | Prise en compte de l’architecture ARM des nœuds GPU et des environnements Spack |
| Comprendre un échec | État du job, extraits ciblés des journaux, diagnostic et efficacité |
| Lancer plusieurs expériences | Tableaux de paramètres, étapes dépendantes et points de reprise |
| Trouver la bonne commande | Documentation embarquée, recherche locale et lecture par section |
| Reprendre une conversation | Registre local des jobs soumis par le MCP |
| Commencer avec peu d’outils | Profil essentiel, avec accès au catalogue complet à la demande |
| Conserver les preuves d’un calcul | Fiche JSON et Markdown : script filtré, code, environnement, ressources et empreintes |

## Comment ça fonctionne

![Du client IA aux nœuds de calcul, via le MCP local, SSH et Slurm](docs/assets/architecture.svg)

1. Votre client IA lance le serveur Python local et lui parle par **stdio**.
2. Le MCP consulte son corpus local ou utilise le client **OpenSSH** de votre poste.
3. Slurm attribue les ressources et exécute les calculs sur les nœuds appropriés.
4. Le MCP restitue au client les états, résultats et extraits demandés.

Le MCP n’embarque aucun modèle IA. Les contenus renvoyés par ses outils peuvent entrer dans le contexte de votre assistant et être transmis à son fournisseur. Choisissez les fichiers et journaux que vous lui donnez en fonction des règles de votre équipe.

## Prise en main

### 1. Préparer les accès

Il vous faut :

- Python **3.11 ou plus**, Git et un client OpenSSH (`ssh -V`).
- Un compte ROMEO actif, une clé SSH enregistrée et un projet de calcul autorisé.
- Un client acceptant les serveurs MCP locaux en stdio.

L’installation automatisée prévoit **Codex**, **Claude Code** et **Claude Desktop**. La disponibilité du MCP dépend aussi de la version et de la configuration de votre client.

Consultez la documentation officielle embarquée pour la [création du compte](romeo_mcp/documentation/creation_compte.md) et la [connexion SSH](romeo_mcp/documentation/SOMMAIRE.md).

Dans `~/.ssh/config` (Windows : `%USERPROFILE%\.ssh\config`), ajoutez une entrée en remplaçant les deux valeurs `VOTRE_…` :

```sshconfig
Host romeo1
    HostName romeo1.univ-reims.fr
    User VOTRE_IDENTIFIANT
    IdentityFile ~/.ssh/VOTRE_CLE_PRIVEE
    IdentitiesOnly yes
```

Testez dans un terminal :

```sh
ssh romeo1
```

Vérifiez l’empreinte de l’hôte selon les instructions ROMEO lors de la première connexion. Une clé protégée par une phrase secrète doit être disponible via votre agent SSH avant de lancer le client IA. Ne copiez jamais la clé privée dans ce dépôt. Fermez cette session avec `exit` après vérification.

### 2. Installer le serveur

**Windows : PowerShell**

```powershell
git clone https://github.com/Gotman08/romeo-mcp.git
cd romeo-mcp
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m romeo_mcp configure --account VOTRE_PROJET --profile essential
.\.venv\Scripts\python.exe -m romeo_mcp doctor
```

**Linux / macOS : terminal**

```sh
git clone https://github.com/Gotman08/romeo-mcp.git
cd romeo-mcp
python3 -m venv .venv
./.venv/bin/python -m pip install -e .
./.venv/bin/python -m romeo_mcp configure --account VOTRE_PROJET --profile essential
./.venv/bin/python -m romeo_mcp doctor
```

**Remplacez `VOTRE_PROJET` par le code de votre projet**, trouvé dans votre espace ROMEO. Ce n’est pas votre identifiant SSH. Aucun compte de calcul n’est fourni par défaut.

`doctor` vérifie la configuration et la présence de la documentation **sans connexion au cluster**. Il doit indiquer `account_configured: true` et des pages documentaires disponibles. Il ne valide pas vos droits Slurm ni votre clé SSH.

Pour vérifier aussi les accès réels, utilisez le Python du même venv :

```sh
python -m romeo_mcp doctor --live
```

Ce diagnostic lit la connexion SSH, l’association au projet Slurm, les partitions et les quotas utilisateur et projet. Chaque contrôle fournit son état et une explication en cas d’échec. Il ne soumet aucun job. [Options et résultats du diagnostic](docs/configuration.md#diagnostic-en-lecture-seule).

La commande `configure` conserve votre choix hors du dépôt :

| Système | Configuration personnelle |
|---|---|
| Windows | `%LOCALAPPDATA%\romeo-mcp\config.json` |
| Linux / macOS | `$XDG_CONFIG_HOME/romeo-mcp/config.json`, sinon `~/.config/romeo-mcp/config.json` |

Un autre alias SSH ou une autre QOS peuvent être indiqués avec `--host` et `--qos`. Les variables d’environnement priment sur le fichier ; voir le [guide de configuration](docs/configuration.md).

### 3. Ajouter le MCP à votre assistant

Depuis la racine du dépôt, choisissez le client voulu :

```powershell
# Windows : inspecter, puis enregistrer dans Codex
.\.venv\Scripts\python.exe tools/install_mcp.py --targets codex --dry-run
.\.venv\Scripts\python.exe tools/install_mcp.py --targets codex
```

```sh
# Linux / macOS : inspecter, puis enregistrer dans Codex
./.venv/bin/python tools/install_mcp.py --targets codex --dry-run
./.venv/bin/python tools/install_mcp.py --targets codex
```

Remplacez `codex` par `claude-code`, `claude-desktop`, ou une liste séparée par des virgules. `--list` affiche les emplacements détectés. L’installateur sauvegarde les fichiers modifiés et vérifie le démarrage du serveur. Relancer l’installation met à jour la même entrée.

Relancez ensuite le client concerné **lorsque vos opérations en cours sont terminées**. Le serveur apparaît sous le nom `romeo`. Pour un autre client stdio ou une configuration manuelle : [exemples de configuration](docs/configuration.md#autres-clients-stdio).

### 4. Faire un premier essai

Commencez par demander à l’assistant :

> Cherche dans la documentation ROMEO comment lancer un calcul CPU. Puis consulte l’état du cluster et mes quotas, sans soumettre de job.

Puis préparez un petit calcul :

> Prépare en simulation un job `hello-romeo`, sur un seul nœud `x64cpu`, avec un cœur, 1 Go de RAM et une minute. La commande est `hostname`. Montre-moi le script et les avertissements avant toute soumission.

L’appel correspondant à `job_prepare` est :

```json
{
  "name": "hello-romeo",
  "command": "hostname",
  "arch": "x64cpu",
  "time_limit": "1m",
  "nodes": 1,
  "cpus_per_task": 1,
  "mem_gb": 1
}
```

La préparation retourne le script et un `plan_id`, sans soumettre le calcul. Elle peut consulter les chemins distants par SSH et conserve le plan localement pendant 24 heures. Après lecture, soumettez exactement ce plan avec `job_submit({"plan_id": "IDENTIFIANT_RECU", "confirm": true})`. Suivez ensuite le job reçu avec `job_status`, `job_log_tail` et `job_efficiency`.

Les tableaux et pipelines suivent le même parcours avec `job_array_prepare` / `job_array_submit` et `job_pipeline_prepare` / `job_pipeline_submit`. Les préparations ne prennent pas de paramètre `confirm`. Un aperçu hors ligne aux chemins illustratifs ne peut pas être soumis. D’autres actions, comme les transferts, l’annulation ou `cluster_gpu_health_run`, agissent directement.

## Des demandes utiles

| Situation | Exemple de demande |
|---|---|
| TP de calcul scientifique | « Prépare un tableau Slurm pour ces paramètres et explique les ressources choisies. » |
| Code MPI | « Trouve le logiciel via Spack, puis prépare un lancement MPI sur deux nœuds. » |
| Calcul GPU | « Vérifie la compatibilité ARM de mes dépendances avant de préparer ce job GPU. » |
| Job en échec | « Analyse le job indiqué et lis seulement les extraits de logs utiles au diagnostic. » |
| Optimisation | « Compare le temps et la mémoire réellement utilisés aux ressources réservées. » |
| Reproductibilité | « Exporte la fiche de ce job avec les empreintes de ces fichiers d’entrée. » |

La [référence technique](docs/reference.md) détaille les outils, MPI, PyTorch, Apptainer, les transferts, le profilage et les limites de chaque mesure.

## Un profil essentiel pour commencer

Le profil `essential` présente **22 outils** : documentation, état du cluster, quotas, logiciels, soumission simple, suivi et diagnostic des jobs, transferts et export de fiches. Il réduit le catalogue envoyé au modèle.

Pour accéder aux tableaux de paramètres, aux pipelines, aux services interactifs ou au profilage, demandez à l’assistant :

> Passe le profil d’outils ROMEO à `full` avec `tool_profile_set`.

Le client reçoit une notification de changement du catalogue. Le choix vaut pour le processus MCP actuel. Pour le conserver au prochain lancement :

```sh
python -m romeo_mcp configure --profile essential
```

Cette commande conserve votre projet et votre alias SSH. Sans choix explicite, le profil reste `full`, pour les opérations métier. Le profil `expert` ajoute les exécuteurs de commandes arbitraires. Les profils modifient la découverte des outils ; les autorisations restent celles du client et de ROMEO. [Liste et configuration des profils](docs/configuration.md#profils-doutils).

## Une fiche de reproductibilité par job

`job_report_export` crée un dossier privé avec `report.json`, `report.md` et `script.sbatch.txt`. Les nouveaux jobs conservent les ressources demandées et tentent de relever le commit Git, l’environnement chargé et les empreintes des fichiers choisis avant le calcul. `job_report_collect(job_id)` enregistre un relevé daté et rend `report_id`. `job_report_export(report_id)` exporte exactement ce relevé, sans SSH.

Pour choisir les entrées à relever au démarrage, ajoutez `data_files` à `job_prepare`. Les fichiers choisis seulement à la collecte sont datés comme observations après coup. Les captures sont limitées à 20 fichiers et 64 Mio par relevé.

Les exports restent **hors des dépôts Git**. Les secrets reconnaissables sont masqués ; le contenu des données, les variables d’environnement complètes et les adresses des dépôts Git ne sont pas exportés. Les informations absentes sont signalées. [Exemples, protection des données et limites](docs/reproducibility.md).

## Documentation locale et contexte de l’IA

Le [corpus ROMEO](romeo_mcp/documentation/SOMMAIRE.md) accompagne le dépôt **et les paquets Python** : 42 pages officielles, 21 images, un sommaire et un manifeste de provenance.

- `search_docs` classe les sections par pertinence lexicale (BM25), avec prise en compte des titres et des accents.
- Les extraits comportent les sources, les lignes, l’empreinte du document et les arguments de lecture.
- `read_doc` permet de lire une section complète. Si elle dépasse le budget, `next_call` poursuit la lecture sans supprimer du texte du corpus.
- Aucun service d’embeddings ni accès réseau n’est requis pour cette recherche.

Un extrait seul peut manquer de prérequis : l’assistant doit poursuivre la lecture de la section ou des sections parentes. Le corpus est daté ; `romeo_status`, `romeo_quota` et `romeo_selfcheck` renseignent l’état actuel du cluster.

Après déplacement du dossier, recréez le venv et relancez l’installateur pour mettre à jour les chemins du client. La documentation reste dans le projet. [Fonctionnement et renouvellement du corpus](docs/reference.md#documentation-hors-ligne).

## Quotas : quel chiffre regarder ?

| Limite | À quoi elle sert |
|---|---|
| Stockage utilisateur | Espace attribué à votre compte sur un système de fichiers |
| Stockage projet | Espace partagé, consommé collectivement par les membres du projet |
| Quota souple / strict | Seuil pouvant ouvrir une période de grâce / plafond bloquant les nouvelles écritures |
| Nombre de fichiers | Limite d’inodes ; beaucoup de petits fichiers peuvent l’atteindre avant le volume en Go |
| CPU / GPU / jobs Slurm | Ressources et nombre de jobs autorisés par les associations et QOS |
| Fairshare | Priorité influencée par l’usage passé du groupe ; ce n’est pas du stockage disponible |

`romeo_quota` lit les quotas effectifs ; `df` indique la capacité du système de fichiers entier. Les plafonds Slurm dépendent du projet. Aucun quota personnel n’est présumé par défaut dans cette version.

## En cas de problème

| Symptôme | Vérification |
|---|---|
| « Projet ROMEO absent » | Exécuter `configure --account …`, puis relancer le processus MCP |
| SSH refusé ou bloqué | Tester `ssh romeo1` dans le même environnement utilisateur ; vérifier clé et agent SSH |
| Le MCP n’apparaît pas | Relancer le client et vérifier le chemin du Python avec `install_mcp.py --list` |
| `No module named romeo_mcp` | Réinstaller avec le Python du venv utilisé par le client |
| Documentation introuvable | Exécuter `doctor` et retirer un ancien `ROMEO_DOCS_DIR` s’il n’est plus valable |
| Un job attend longtemps | Lire le motif Slurm ; vérifier disponibilité, compte, QOS, dépendances et limites |
| Binaire incompatible sur GPU | Recompiler pour `aarch64` sur un nœud adapté avec `compute_command_prepare` |

## Contribuer et vérifier

```sh
python tests/run_all.py
python tools/check_privacy.py --history
```

Utilisez le Python du venv. Les suites par défaut sont hors ligne. Les tests `--live` demandent un accès ROMEO et **peuvent soumettre de vrais jobs** ; ils sont exclus de la CI.

La CI vérifie les suites hors ligne, la documentation, les métadonnées de commit et les fichiers publiés, puis construit le paquet. Les procédures de contribution et de signalement se trouvent dans [CONTRIBUTING.md](CONTRIBUTING.md) et [SECURITY.md](SECURITY.md).

Code distribué sous [licence MIT](LICENSE). La documentation et les visuels officiels conservent leurs droits et leur attribution : [contenus tiers](THIRD_PARTY_NOTICES.md).
