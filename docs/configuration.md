# Configuration

[Accueil](../README.md) › [Documentation](README.md) › Configuration

<details>
<summary>Sommaire de cette page</summary>

- [Votre profil ROMEO](#votre-profil-romeo)
- [Profils d’outils](#profils-doutils)
- [Diagnostic en lecture seule](#diagnostic-en-lecture-seule)
- [Autres clients stdio](#autres-clients-stdio)
- [Reprendre automatiquement les préférences du client](#reprendre-automatiquement-les-préférences-du-client)
- [Déplacer ou mettre à jour l’installation](#déplacer-ou-mettre-à-jour-linstallation)
- [WSL](#wsl)

</details>

## Votre profil ROMEO

`python -m romeo_mcp configure --account VOTRE_PROJET --host romeo1 --qos normal`
enregistre trois identifiants non secrets dans un fichier personnel hors du
dépôt. Remplacez le code projet avant exécution. Le serveur lit ce fichier au
démarrage. Les processus existants conservent leur configuration jusqu’à leur
prochain lancement.

Priorité : **variable d’environnement → fichier personnel → valeur par défaut**.
Une variable vide reste une surcharge explicite, notamment pour désactiver le
compte configuré. Le fichier ne contient ni clé SSH ni mot de passe.

| Variable | Valeur par défaut | Rôle |
|---|---|---|
| `ROMEO_CONFIG` | Fichier utilisateur décrit dans le README | Autre fichier de profil ; le garder hors du dépôt |
| `ROMEO_ACCOUNT` | Aucune | Projet Slurm autorisé ; obligatoire pour préparer une allocation |
| `ROMEO_HOST` | `romeo1` | Alias dans votre configuration OpenSSH |
| `ROMEO_QOS` | `normal` | QOS autorisée pour le projet |
| `ROMEO_TOOL_PROFILE` | `full` | Catalogue annoncé : `essential`, `full` ou `expert` |
| `ROMEO_AUTO_UPDATE` | Accord local, désactivé initialement | `1` autorise les installations automatiques ; `0` les bloque, même après un accord enregistré |
| `ROMEO_UPDATE_CHECK` | `1` | `0` désactive le contrôle au démarrage ; les outils et le CLI restent utilisables |
| `ROMEO_UPDATES_DIR` | Dossier utilisateur hors Git | Racine des versions isolées, de la politique et des observations |
| `ROMEO_AUTO_ISSUES` | Accord local, désactivé initialement | `1` autorise les rapports GitHub automatiques ; `0` désactive ces envois |
| `ROMEO_REPORTS_DIR` | `issue-reports/` à côté de `ROMEO_CONFIG` | Registre SQLite privé et autorisation persistante, obligatoirement hors Git |
| `ROMEO_GITHUB_TOKEN` | Connexion GitHub CLI si disponible | Jeton d'environnement privé pour les issues ; jamais enregistré dans le profil ou les rapports |
| `ROMEO_MAX_CPUS`, `ROMEO_MAX_GPUS`, `ROMEO_MAX_JOBS` | `0` | Seuils locaux indicatifs ; `0` signifie inconnu, sans avertissement de dépassement |
| `ROMEO_MCP_DB` | `~/.romeo-mcp/jobs.db` | Registre privé des jobs et scripts soumis |
| `ROMEO_SCRATCH`, `ROMEO_HOME` | Découverts par SSH | Racines distantes ; permettent aussi une simulation hors ligne |
| `ROMEO_DOCS_DIR` | Corpus dans le paquet | Corpus externe facultatif ; chemin relatif à la racine d’installation |

Les seuils locaux ne changent pas les droits Slurm. La limite effective peut
venir du projet, de l’utilisateur, de la partition ou de la QOS. Les plafonds
CPU/GPU configurés alimentent les avertissements de planification ; le seuil
de jobs sert à la comparaison de [`romeo_selfcheck`](tools/romeo_selfcheck.md).

Pour travailler sur plusieurs projets, utilisez des profils externes et une
entrée MCP distincte par profil avec `ROMEO_CONFIG`. Une seule instance charge
un seul profil. `configure` enregistre un fichier mais ne modifie pas les
variables déjà définies dans le client.

## Profils d’outils

| Profil | Outils annoncés |
|---|---|
| `essential` | [`tool_profile_get`](tools/tool_profile_get.md), [`tool_profile_set`](tools/tool_profile_set.md), [`search_docs`](tools/search_docs.md), [`read_doc`](tools/read_doc.md), [`romeo_status`](tools/romeo_status.md), [`romeo_quota`](tools/romeo_quota.md), [`romeo_software`](tools/romeo_software.md), [`job_prepare`](tools/job_prepare.md), [`job_submit`](tools/job_submit.md), [`job_status`](tools/job_status.md), [`job_log_tail`](tools/job_log_tail.md), [`job_log_search`](tools/job_log_search.md), [`list_jobs`](tools/list_jobs.md), [`cancel_job`](tools/cancel_job.md), [`diagnose_job`](tools/diagnose_job.md), [`job_efficiency`](tools/job_efficiency.md), [`list_dir`](tools/list_dir.md), [`upload_to_romeo`](tools/upload_to_romeo.md), [`download_from_romeo`](tools/download_from_romeo.md), [`job_report_collect`](tools/job_report_collect.md), [`job_report_export`](tools/job_report_export.md), [`plan_get`](tools/plan_get.md) |
| `full` | Catalogue métier : tableaux, pipelines, services, environnements, fichiers et rapports |
| `expert` | Catalogue `full` plus [`compute_command_prepare`](tools/compute_command_prepare.md), [`compute_command_run`](tools/compute_command_run.md) et [`login_command_run`](tools/login_command_run.md) |

Trois façons de choisir :

```sh
# Enregistrer le choix pour les prochains lancements, sans modifier les accès
python -m romeo_mcp configure --profile essential

# Imposer le profil à un seul processus stdio
python -m romeo_mcp serve --profile essential
```

Pendant une conversation, l’outil `tool_profile_set({"profile": "full"})` change le
catalogue du processus actuel et émet `notifications/tools/list_changed`.
`tool_profile_get()` consulte le profil et les outils annoncés sans modifier le catalogue. Certains clients
gardent leur catalogue en cache : relire `tools/list` ou relancer le MCP si
les outils avancés n’apparaissent pas.

La priorité du démarrage est **`serve --profile` → `ROMEO_TOOL_PROFILE` →
fichier personnel → `full`**. Le choix fait avec [`tool_profile_set`](tools/tool_profile_set.md) ne modifie
aucun fichier. Un profil réduit la liste présentée au modèle ; il ne constitue
pas une restriction de sécurité. Les gestionnaires avancés restent enregistrés.

## Diagnostic en lecture seule

```sh
python -m romeo_mcp doctor
python -m romeo_mcp doctor --live
python -m romeo_mcp doctor --live --timeout 30 --project-group VOTRE_GROUPE_GPFS
```

`doctor` vérifie localement Python, le SDK, la configuration et le corpus.
`--live` ajoute cinq lectures, dans une connexion SSH dédiée fermée à la fin :

| Contrôle | Source | Si le contrôle échoue |
|---|---|---|
| SSH | `id -un` | Vérifier réseau, alias, clé et agent SSH ; les lectures suivantes sont ignorées |
| Projet Slurm | `sacctmgr show assoc` | Vérifier le code projet et l’association de votre utilisateur |
| Partitions | `sinfo` | Vérifier les partitions ouvertes et les annonces de maintenance |
| Quota utilisateur | `mmlsquota -u` | Vérifier GPFS, les droits et les délais de grâce |
| Quota projet | `mmlsquota -g` | Vérifier le groupe de stockage, qui peut différer du projet Slurm |

Le groupe GPFS vaut par défaut le projet configuré. `--project-group` permet
de le remplacer pour ce diagnostic. Les quotas portent sur le volume et, si
présentes dans la réponse, les limites de fichiers. Les valeurs restent
celles rapportées par GPFS ; une période de grâce active produit un avertissement.

Le résultat JSON contient `ok`, `read_only`, une date et une liste `checks`,
avec `status`, `code` et `message`. Code de sortie **0** si tous les contrôles
distants réussissent, **1** en cas d’erreur, d’avertissement ou de diagnostic
incomplet. `--timeout` borne chaque lecture entre 2 et 60 secondes ; plusieurs
lectures peuvent donc prendre plus longtemps au total, en plus de l’ouverture SSH.

Aucun `sbatch`, `srun`, transfert de données ou changement de quota n’est
exécuté. OpenSSH peut toutefois enregistrer un nouvel hôte dans `known_hosts`
selon sa configuration. Voir des partitions ouvertes ne garantit pas qu’un
job donné soit accepté : QOS, limites et ressources disponibles restent applicables.

## Autres clients stdio

Exemple pour les clients utilisant la forme JSON `mcpServers`. Adaptez le
chemin absolu et la structure aux instructions de votre client :

```json
{
  "mcpServers": {
    "romeo": {
      "command": "/chemin/vers/romeo-mcp/.venv/bin/python",
      "args": ["-m", "romeo_mcp"]
    }
  }
}
```

Sur Windows, utilisez par exemple
`C:/chemin/vers/romeo-mcp/.venv/Scripts/python.exe`. Les barres obliques évitent
les échappements JSON. Le paquet doit avoir été installé avec ce Python.

L’installateur fourni gère les formats des trois clients documentés. Pour
Codex, il écrit une section `[mcp_servers.romeo]` dans le fichier utilisateur
`config.toml`. Il ajoute `PYTHONPATH` vers le dépôt pour permettre le démarrage
depuis n’importe quel répertoire et conserve les réglages existants de Romeo,
notamment ses outils désactivés, ses délais et ses règles d’approbation.

## Reprendre automatiquement les préférences du client

À chaque installation ou reconfiguration, `tools/install_mcp.py` lit les choix
enregistrés dans le client. Pour Codex :

| Choix enregistré | Comportement de l’installateur |
|---|---|
| Mode d’approbation explicite pour Romeo | Le conserver, ainsi que les règles propres à chaque outil |
| `approval_policy = "never"` **et** `sandbox_mode = "danger-full-access"` | Utiliser `default_tools_approval_mode = "approve"` pour Romeo |
| Autre mode, choix incomplet ou profil inconnu | Utiliser `auto`, le comportement normal du client |

Le profil sélectionné par `profile` dans `config.toml` est pris en compte.
`never` seul ne donne aucune autorisation supplémentaire : dans un environnement
restreint, une opération qui aurait besoin d’approbation peut être refusée.

Un commentaire `romeo-mcp: client-approvals=...` identifie le réglage calculé.
À la prochaine exécution de l’installateur, celui-ci est recalculé, y compris
si le client est devenu plus restrictif. Un mode modifié manuellement prend
la priorité. Pour remplacer un ancien choix propre à Romeo par cette reprise
automatique des préférences :

```sh
python tools/install_mcp.py --targets codex --follow-client-approvals --dry-run
python tools/install_mcp.py --targets codex --follow-client-approvals
```

La simulation indique le mode retenu sans écrire de fichier. L’installation
sauvegarde le fichier avant modification. Les règles par outil et les listes
d’outils autorisés ou désactivés sont conservées, même avec cette option.

Claude Code applique directement `permissions.defaultMode` et ses règles
`allow`, `ask` et `deny`. L’installateur conserve ces préférences ; il n’ajoute
pas d’autorisation implicite à partir de `dontAsk`, qui refuse les opérations
non autorisées. Les autorisations de Claude Desktop restent gérées dans ce client.

Cette adaptation intervient **à l’installation ou à la reconfiguration**.
Le protocole MCP ne transmet pas une politique d’approbation standard au serveur.
Romeo ne réécrit donc pas la configuration pendant un appel. Les changements
temporaires de session et les restrictions administratives restent appliqués
par le client ; après un changement de préférences enregistrées, relancer
l’installateur, puis recharger la configuration du client.

Références : [configuration Codex](https://developers.openai.com/ja-JP/docs/config-file/config-reference),
[autorisations Claude Code](https://code.claude.com/docs/en/permissions) et
[initialisation MCP](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle).

## Déplacer ou mettre à jour l’installation

1. Terminer les appels MCP en cours avant de relancer le client.
2. Conserver les fichiers personnels externes et le registre des jobs.
3. Mettre à jour le dépôt ; après déplacement, recréer le venv au nouvel endroit.
4. Installer le paquet avec le Python de ce venv.
5. Relancer `tools/install_mcp.py --targets CLIENT` et vérifier avec `doctor`.
6. Relancer le client quand il peut charger la nouvelle version.

Arrêter un client MCP n’annule pas les jobs déjà soumis à Slurm. Utilisez
[`cancel_job`](tools/cancel_job.md) uniquement pour les jobs que vous voulez réellement annuler.

## WSL

Préférez un ensemble cohérent : Python, SSH, clés et configuration du client
dans le même environnement. L’installateur détecte WSL et peut traduire les
chemins pour les clients Windows, mais les agents SSH et les clés ne sont pas
automatiquement partagés entre Windows et Linux. Vérifiez `ssh romeo1` depuis
l’environnement qui lancera effectivement le serveur.

---

[↑ Haut de page](#configuration) · [Accueil](../README.md) · [Documentation](README.md) · [Catalogue Tools](Tools.md)
