# Tests et niveaux de vérification

[Accueil](../README.md) › [Documentation](../docs/README.md) › Tests

Ce dossier vérifie les règles du serveur, le protocole MCP et, sur demande
explicite, son fonctionnement sur ROMEO. Toutes les commandes ci-dessous se
lancent depuis la **racine du dépôt**, avec le Python du venv activé.

<details>
<summary>Sommaire de cette page</summary>

- [Commencer hors ligne](#commencer-hors-ligne)
- [Suites hors ligne](#suites-hors-ligne)
- [Essais sur ROMEO](#essais-sur-romeo)
- [Interpréter un succès](#interpréter-un-succès)
- [Continuer](#continuer)

</details>

## Commencer hors ligne

```sh
python tests/run_all.py
python tests/run_all.py --only docs
python tests/run_all.py --only accompagnement
python tests/run_all.py --only terminal
python tests/run_all.py --only issue-reports
python tests/run_all.py --only energy
python tools/check_tool_docs.py
```

Sans option, le lanceur exécute les suites hors ligne dans des processus séparés et
affiche un bilan. Il retourne un code non nul si une suite échoue. Les suites
hors ligne utilisent une configuration fictive et ne nécessitent pas d’accès
SSH au calculateur.

## Suites hors ligne

La suite `issue-reports` vérifie les appels GitHub simulés, le filtrage avant
stockage/envoi, les doublons, les coupures et l'accord persistant à travers un
vrai client MCP stdio. Elle ne crée aucune issue réelle et n'utilise pas SSH.
Elle vérifie aussi l'absence de texte libre et d'empreinte privée dans la
publication, le choix du compte bot local ou personnel et la suppression locale.

La suite `energy` vérifie la conversion des compteurs, l'attribution au job,
les valeurs inconnues et la couverture temporelle du facteur RTE, avec des
données fictives. `tool-docs` compare les exemples JSON, paramètres, défauts
et liens source des 99 outils au catalogue MCP complet, sans appeler les outils.

Le [tableau de bord terminal facultatif](../docs/terminal.md) possède aussi des
tests Rust : `cargo test --locked --manifest-path terminal/Cargo.toml`.
La suite Python `terminal` vérifie le lecteur sans nécessiter Cargo ou le cluster.
Elle vérifie aussi l'association et l'âge des checkpoints, les mesures rsync
bornées, la lecture seule des rapports et l'absence de publication réseau.
Les tests Rust couvrent les filtres propres à chaque vue, les pages, les détails
défilants et le format compact, ainsi que la recherche accentuée, les tris et la
sélection, les erreurs Slurm et la séparation calcul/validation. Le test PTY
Linux simule un lecteur interrompu puis bloqué pour vérifier sa récupération
et son arrêt après le délai, et inspecte les couleurs ANSI dans les modes
`auto`, `always` et `never`, y compris avec un `NO_COLOR` hérité.

| Nom pour `--only` | Fichier | Ce qui est vérifié |
|---|---|---|
| `units` | [test_units.py](test_units.py) | Durées, ressources, partitions, scripts et garde-fous |
| `workloads` | [test_workloads.py](test_workloads.py) | Lanceurs, gabarits, diagnostics et modèles matériels |
| `regressions` | [test_regressions.py](test_regressions.py) | Corrections de défauts déjà rencontrés |
| `confined-paths` | [test_confined_paths.py](test_confined_paths.py) | Noms exacts, racines physiques, changements de liens et transferts conservant leurs descripteurs ; cas POSIX exécutés sur Linux |
| `job-io` | [test_job_io.py](test_job_io.py) | Huit tableaux soumis simultanément dans le même dossier, scripts isolés, empreintes et lecture des journaux |
| `tool-actions` | [test_tool_actions.py](test_tool_actions.py) | Contrats MCP, effets annoncés, plans persistants, scripts exacts, appels concurrents et reprise après échec |
| `lifecycles` | [test_lifecycles.py](test_lifecycles.py) | Parcours des services, allocations, environnements Python et fichiers |
| `ajouts` | [test_ajouts.py](test_ajouts.py) | Pipelines et confrontation du modèle de cluster |
| `docs` | [test_docs.py](test_docs.py) | Recherche, sections, pagination, portabilité et protocole documentaire |
| `setup` | [test_setup.py](test_setup.py) | Configuration personnelle, installation et confidentialité |
| `accompagnement` | [test_accompagnement.py](test_accompagnement.py) | Profils d’outils, diagnostic simulé, filtrage et reproductibilité |
| `updates` | [test_updates.py](test_updates.py) | Intégrité des releases, confirmation, installation isolée réelle sans réseau, stdio et retour arrière avec processus actif |
| `update-tools` | [test_update_tools.py](test_update_tools.py) | Accord automatique, erreurs explicites, absence de doublons, interruptions, écartement après retour et outils par stdio |
| `issue-reports` | [test_issue_reports.py](test_issue_reports.py) | Projection publique fermée, choix du compte et suppression locale ; GitHub simulé |
| `energy` | [test_energy.py](test_energy.py) | Compteurs Slurm, exclusivité, unités, facteurs datés et absence de données |
| `tool-docs` | [check_tool_docs.py](../tools/check_tool_docs.py) | Exemples, paramètres, défauts et liens comparés aux contrats MCP |
| `corpus` | [verify_corpus.py](../tools/verify_corpus.py) | Liens, images, accessibilité et empreintes de la documentation |

Les appuis partagés se trouvent dans [commun.py](commun.py) et
[offline.py](offline.py). La liste de référence des suites est dans
[run_all.py](run_all.py).

La suite `job-io` exécute les commandes Bash sur des fichiers temporaires
locaux ; SSH et l'ordonnanceur Slurm sont simulés. Elle utilise Bash sur Unix
ou Git Bash sur Windows et indique explicitement une suite ignorée si ce
shell manque. Les huit tableaux partagent le même nom et le même dossier,
et leurs tâches ne démarrent qu'après toutes les soumissions.

La suite `updates` construit une wheel de test et l’installe dans un venv
temporaire avec `pip --no-index --no-deps`. Elle vérifie les erreurs avant
activation et le lancement de la version choisie. Les requêtes GitHub sont
simulées ; la notification réseau au démarrage est désactivée dans les suites.

## Essais sur ROMEO

Ces suites nécessitent un compte autorisé et une configuration SSH fonctionnelle.
Certaines soumettent des jobs ou réservent des ressources. L’option `--only`
lance aussi une suite distante lorsqu’on la nomme explicitement.

| Nom pour `--only` | Fichier | Périmètre |
|---|---|---|
| `protocol` | [smoke_protocol.py](smoke_protocol.py) | Connexion stdio, inventaire MCP et lecture de l’état réel du cluster |
| `ssh` | [smoke_ssh.py](smoke_ssh.py) | Transport SSH persistant |
| `live` | [smoke_live.py](smoke_live.py) | Soumission, suivi et efficacité de jobs réels |
| `repro-live` | [smoke_repro_live.py](smoke_repro_live.py) | Petit calcul CPU, provenance, empreintes et exports par MCP |
| `workloads-live` | [smoke_workloads_live.py](smoke_workloads_live.py) | Tableaux, diagnostics de jobs en échec et observation distante |

Un essai ciblé de reproductibilité :

```sh
python tests/run_all.py --only repro-live
```

Il demande un cœur, 1 Go et une minute au maximum pour le job. Le registre et
les rapports restent dans `~/.romeo-mcp/test-runs/` ; les petits fichiers
distants sont conservés pour le diagnostic. Pour reprendre sa vérification
après une interruption, sans soumettre à nouveau :

```sh
python tests/smoke_repro_live.py --resume DOSSIER_DU_TEST
```

`python tests/run_all.py --live` ajoute toutes les suites distantes au parcours
complet. Pour une simple vérification des accès, utiliser plutôt le
[diagnostic en lecture seule](../docs/configuration.md#diagnostic-en-lecture-seule).

## Interpréter un succès

Une suite hors ligne valide les comportements couverts par ses cas. Un test
stdio valide le dialogue avec le serveur. Un essai réel ajoute des observations
du cluster à cet instant. La validation scientifique d’un calcul dépend des
résultats attendus de l’expérience concernée.

Pour publier un résultat de test, préciser la commande, la version et le
périmètre vérifié. Les comptes, journaux privés et résultats scientifiques
personnels restent hors du dépôt.

## Continuer

[CI sur Windows et Linux](../.github/workflows/README.md) ·
[Contrôles avant publication](../tools/README.md#vérifier-avant-de-publier) ·
[Règles de contribution](../CONTRIBUTING.md)

---

[↑ Haut de page](#tests-et-niveaux-de-vérification) · [Accueil](../README.md) · [Documentation](../docs/README.md) · [Catalogue Tools](../docs/Tools.md)

## Fraicheur et operations persistantes

`python tests/run_all.py --only observability` verifie les caches expires, les ecritures SSH ambigues, les observations persistantes, les transferts consommables une fois et l annulation de processus locaux jetables. Si rsync est installe, elle copie aussi un fichier local reel pour verifier les mesures de progression en cours et en fin de copie, sans affirmer une verification d'integrite. Cette suite est incluse dans la commande hors ligne par defaut.

La suite `checkpoints` verifie les fichiers reels, les preuves par rang, les quotas et exports. Les tests POSIX utilisent de vrais processus avec un lanceur srun de test ; les contrats purs passent aussi sous Windows. Aucun job ROMEO ne tourne dans cette suite.
