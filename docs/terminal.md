# Tableau de bord terminal (version interne 0.4)

[Accueil](../README.md) · [Documentation](README.md) · [Mesures](terminal-performance.md)

Cette interface facultative utilise [Ratatui](https://ratatui.rs/) et s'ouvre
uniquement sur demande. Le lancement habituel de `romeo-mcp` reste le serveur
MCP en stdio. Il ne lance pas d'interface et ne requiert ni Rust ni Cargo.

## Premier essai

Installer [Rust avec rustup](https://rustup.rs/) (Rust 1.88 ou supérieur).
Sous Windows, la compilation nécessite les outils C++ de Visual Studio et le
SDK Windows ; sous Linux, un compilateur/linker C, par exemple `cc`.
Python 3.11 ou supérieur est nécessaire pour le lecteur des données.

Depuis le dépôt :

```console
python -m romeo_mcp tui --build --demo
python -m romeo_mcp tui --demo --color always
python -m romeo_mcp tui
```

`--build` compile explicitement le binaire avec les dépendances verrouillées
dans `terminal/Cargo.lock`. Cargo télécharge les dépendances manquantes à ce
moment-là seulement. Relancer `--build` après une modification des sources Rust.
Les lancements suivants réutilisent le binaire.

`--color auto` est le défaut : une variable `NO_COLOR` non vide désactive la
palette. `always` active les couleurs même si cette variable est héritée du
lanceur ; `never` choisit le mode monochrome. Le bandeau indique la raison du
mode monochrome. Ce réglage concerne seulement le processus d'interface.

`--demo` affiche des jobs, transferts, checkpoints, rapports et versions
**fictifs**, sans lire le registre ou la configuration ROMEO de l'utilisateur.
Sans cette option, le tableau présente les traces locales de cette installation.

`romeo-mcp tui` fonctionne aussi lorsque le paquet est installé. Le wheel reste
indépendant de Rust et ne contient pas de binaire natif : compiler depuis le
dépôt ou une archive source, puis passer `--binary CHEMIN` ou définir
`ROMEO_TUI_BINARY`. Le lanceur cherche ensuite le binaire du dépôt, un binaire
`romeo-tui` voisin du Python utilisé, puis dans `PATH`. Le binaire voisin
fonctionne aussi sans activation du venv.

Le contrat courant est le **schéma 3** (pages et compteurs globaux). Le lecteur
conserve le schéma 2 pour un ancien tableau 0.3 déjà ouvert ; relancer le tableau
pour profiter de toutes les nouveautés. Une incompatibilité est signalée dans
les alertes : recompiler le binaire et relancer.

## Navigation

| Touche | Action |
|---|---|
| `1` à `5`, `Tab`, Maj-Tab, `←` / `→` | Choisir Aperçu, Jobs, Transferts, Mises à jour ou Rapports |
| `↑` / `↓`, `j` / `k`, Début / Fin | Sélectionner une ligne ou une alerte ; faire défiler le panneau actif ou les mises à jour |
| Page précédente / suivante | Se déplacer d'une hauteur de fenêtre dans les lignes chargées ou le panneau actif |
| `n` / `b` | Charger la page suivante / précédente du registre ou des alertes |
| `/` | Saisir une recherche propre à Jobs, Transferts ou Rapports ; le premier caractère remplace le filtre précédent |
| Entrée | Valider la saisie ; ouvrir le détail complet d'une ligne ; depuis une alerte, rejoindre exactement sa trace |
| `s` | Changer le tri global : actifs, date, état, priorité ; chaque vue conserve son tri et l'identifiant sélectionné |
| `v` | Choisir liste seule / liste et détail |
| F6 | Activer la liste / le détail défilant ; le titre indique le panneau actif |
| `[` / `]` | Réduire / augmenter la largeur du détail par pas de 5 %, entre 25 et 65 % |
| `c` / `C` | Copier l'identifiant / le chemin local d'un transfert dans le presse-papiers |
| `e` | Exporter un résumé UTF-8 dans le dossier local du tableau ; `!` montre le chemin complet |
| Échap | Fermer un panneau ; dans une liste, effacer le filtre et quitter sa saisie |
| `r` | Forcer une relecture locale, même en pause ; reconnecter un lecteur interrompu |
| `p` | Suspendre/reprendre la relecture automatique |
| `?` | Ouvrir/fermer l'aide |
| `!` | Lire le détail des erreurs, avertissements et notifications locales |
| `q`, Ctrl-C | Quitter et restaurer le terminal |

Un format de 100 colonnes sur 30 lignes est confortable. En dessous de 48 × 16,
un message invite à agrandir le terminal. Le mode compact réserve l'espace à la
liste ; Entrée ouvre un détail défilant. À partir de 128 colonnes, les panneaux
sont côte à côte ; en dessous, ils sont superposés. La largeur réglable concerne
les panneaux côte à côte. Les panneaux et listes qui débordent affichent une
barre de défilement ; le panneau actif indique sa plage de lignes.

La recherche couvre **tout le registre local**, et non la seule page affichée.
Elle porte sur identifiants, noms, chemins, libellés français et états techniques.
Majuscules, accents et Unicode décomposé sont normalisés : « en cours »,
« termine » et « completed » retrouvent les transferts correspondants.
« Récent », « ancien » et « absent » retrouvent aussi la fraîcheur des traces.

Les Jobs sont triés par activité par défaut : un ancien job actif reste
prioritaire. Le tri par date utilise l'observation, puis la soumission ou la
création du plan en l'absence d'observation ; les dates absentes viennent en
dernier. La priorité place les échecs, les traces à examiner, les opérations
actives puis les autres traces. Un identifiant départage les égalités.
Le tri est fixé au relevé : le vieillissement d'une observation ne déplace pas
la sélection entre deux lectures. Une nouvelle lecture conserve l'identifiant
sélectionné, même s'il change de page.

Une lecture lente n'empêche pas de naviguer ou de quitter. L'inventaire affiche
le nombre d'éléments effectivement lus pendant un gros chargement. Après
10 secondes sans réponse **ni progression d'inventaire**, le lecteur détenu par
le tableau est arrêté et les dernières données restent affichées. `r` reconnecte
le lecteur. Une réponse associée à un ancien filtre est écartée puis remplacée
par la dernière demande. Ces lectures ne relancent aucune opération ROMEO.

## Données et preuves affichées

- **Aperçu** : compteurs et alertes de l'inventaire complet, indépendants des
  filtres et pages des Jobs/Transferts. Sélectionner une alerte puis Entrée
  rejoint son job, transfert ou rapport et ouvre le détail. Les transferts
  terminés sans validation et les opérations actives sans observation récente
  figurent parmi les traces à vérifier.
- **Jobs** : dernière observation Slurm sauvegardée, soumission, durées et code
  de sortie connus. Une observation de service ne remplace pas celle de Slurm.
  Les colonnes **Calcul** et **Résultat** séparent « Terminé » et « Vérifié / À
  vérifier ». Libellés et couleurs sont communs aux vues, notamment pour
  `NODE_FAIL` et `OUT_OF_MEMORY`. Le détail regroupe État, Temps, Ressources HPC,
  Checkpoint et Validation, avec dates exactes en UTC. Un `—` signifie qu'une
  valeur manque. Nœuds, tâches Slurm, CPU par tâche, threads OpenMP et GPU sont
  affichés lorsqu'ils sont enregistrés. Les demandes numériques du script
  sauvegardé sont séparées des valeurs observées dans Slurm ; le script n'est
  ni exécuté ni exporté. Les rangs MPI d'un checkpoint proviennent de son
  observation associée au job, à l'exécution, aux empreintes et aux rangs.
- **Transferts** : plan vérifié, état du worker, phase, chemins, progression
  mesurée et date du dernier signal de vie enregistré. La colonne **Intégrité**
  reste distincte de **Copie**, y compris en petit terminal : une copie à 100 %
  peut rester « À vérifier ». Une demande d'annulation ne prouve pas l'arrêt.
  Un statut ancien ne prouve pas qu'un worker est encore actif. Les plans
  altérés et observations d'un autre transfert sont écartés. Pourcentage,
  barre, débit et estimation viennent exclusivement des mesures enregistrées.
  Une mesure absente ou incohérente ne remplit aucune barre.
- **Mises à jour** : version du lecteur, sélection au prochain lancement,
  dernier contrôle GitHub en cache, autorisation et phase sauvegardées. Un
  cache absent ou en erreur laisse la disponibilité inconnue.
- **Rapports** : autorisation automatique effective, état de publication,
  occurrences, date exacte et lien GitHub déjà enregistré. La vue ne contrôle
  pas à nouveau l'issue et ne collecte ni jeton, description complète ou journal.

Les badges **Récent / Ancien / Absent / Date future** utilisent les dates des
preuves, jamais la date de relecture. Les seuils par défaut sont 300 secondes
pour les jobs et 60 pour les transferts. `--job-stale-after` et
`--transfer-stale-after` les règlent indépendamment (1 à 86 400 secondes).
Une date future incohérente reste une alerte. Les listes larges et les détails
affichent ces badges ; les petites listes privilégient état et validation.

Les nouveaux transferts détachés utilisent `rsync --info=progress2` si rsync
local est en version 3.1 ou supérieure. L'inventaire initial complet peut
consommer davantage de mémoire sur un gros répertoire. Le pourcentage arrondi
fourni par rsync n'est pas converti en taille totale prétendument exacte. Sans
mesures (scp, ancien rsync ou ancien statut), la progression reste non mesurée.
Ces statistiques sont enregistrées par le worker sans sondage SSH supplémentaire.
Les transferts synchrones conservent leur comportement.

## Couverture et coût des lectures

Le lecteur indexe les traces utiles de **tous les jobs et dossiers de transfert**
locaux dans une base privée en mémoire. Le registre de rapports lui-même est
limité à 1 000 rapports. Une page contient 40 lignes par défaut ; `--limit`
accepte 1 à 100. Le titre indique **chargés / total** et **page / pages** ; le
filtre précise le nombre de correspondances. Aucun compteur de l'Aperçu n'est
limité à la page affichée.

La relecture intervient toutes les 5 secondes (`--refresh` : 1 à 300). Le lecteur
réutilise les lignes indexées et surveille les signatures des sources, y compris
le WAL SQLite. Seuls les transferts modifiés sont reparsés. Les métadonnées des
fichiers sont encore vérifiées à chaque lecture pour détecter une écriture en
place. Le cache JSON garde au plus 2 048 entrées et 8 Mio de tailles sérialisées ;
l'index global croît avec le nombre de traces. Recherche et tri s'appliquent à
cet index puis les pages bornées sont transmises au rendu.
[Méthode, résultats et limites des mesures](terminal-performance.md).

Une source illisible produit un avertissement et conserve les dernières traces
lisibles de cette source. Une trace de transfert altérée est écartée avec alerte.
Les fichiers JSON et observations sont bornés. Le tableau ne crée pas le registre
de jobs. `ROMEO_MCP_DB` ou `--db CHEMIN` permettent de le choisir en lecture seule.

**La relecture est locale.** Elle n'interroge ni SSH, Slurm, Spack ou GitHub et
ne lance aucune opération distante. Demander à l'assistant d'utiliser les outils
MCP pour actualiser les observations du cluster ; le tableau relira leurs traces.
Les cibles des anciennes observations ne sont pas comparées à la cible SSH
actuelle : les états restent un historique daté. Les mises à jour affichées
concernent seulement l'installation qui lance le tableau.

## Préférences et actions locales

Vue, tris, disposition, largeur et seuils sont mémorisés dans
`~/.romeo-mcp/viewer/preferences.json` (`demo.json` pour la démonstration).
`--preferences CHEMIN` choisit un fichier ; `--no-preferences` désactive cette
mémorisation. Les options de lancement priment sur les réglages sauvegardés.
Filtres, sélection et identifiants SSH ne sont pas sauvegardés. Les préférences
corrompues sont signalées et les réglages par défaut sont utilisés.

Les exports concernent la ligne sélectionnée, ou la page d'alertes affichée.
Ils vont dans `~/.romeo-mcp/viewer/exports/` ; `--export CHEMIN` permet un export
sans terminal interactif. Un fichier existant n'est jamais écrasé. Sous Linux,
la copie utilise `wl-copy`, `xclip` ou `xsel` s'ils sont disponibles ; sous macOS,
`pbcopy` ; sous Windows, PowerShell. Une indisponibilité est signalée et l'export
reste utilisable. Les helpers de copie détenus par le tableau ont un délai de
deux secondes et sont arrêtés à l'expiration.

Clés SSH, utilisateurs, codes projet, scripts et jetons ne font pas partie du
contrat d'affichage. Les noms et chemins peuvent être privés, y compris dans
les exports : utiliser `--demo` pour une capture publique. Les caractères de
contrôle sont neutralisés avant affichage. La relecture ne change aucune
configuration MCP ; préférences et exports sont les écritures locales explicites
du tableau.

## Rendu sans terminal et développement

```console
python -m romeo_mcp tui --demo --snapshot --view jobs --width 100 --height 30
python -m romeo_mcp tui --demo --json
python -m romeo_mcp tui --json --view jobs --query "en cours" --page 1
python -m romeo_mcp tui --view jobs --layout list --sort priority
python -m romeo_mcp tui --view transfers --export resume-transfert.txt
```

`--snapshot` utilise réellement le backend de test Ratatui pour produire un
rendu texte. `--json` fournit le relevé versionné sans binaire Rust. Ces modes
et `--export` n'écrivent pas les préférences. Des flux redirigés sont refusés
avant l'activation du mode brut pour un lancement interactif. Aucune sortie de
tableau n'est ajoutée au protocole MCP.

`terminal_data.py`, `terminal_evidence.py` et `terminal_hpc.py` définissent les
sources et preuves compactes ; `terminal_catalog.py` et `terminal_cache.py`
isolent index, pages et invalidation. `transfer_progress.py` extrait les mesures
numériques des journaux rsync par blocs bornés, sans exporter le texte du journal.
`terminal.py` gère lancement et compilation. Les modules Rust `model`, `status`,
`query`, `color`, `app`, `ui`, `preferences`, `local` et `bridge` séparent les
responsabilités. Un seul lecteur Python isolé est détenu par l'interface, avec
canaux bornés ; il est arrêté et récolté à la fermeture du tableau.

```console
python tests/run_all.py --only terminal
python tests/run_all.py --only terminal-catalog
cargo fmt --manifest-path terminal/Cargo.toml -- --check
cargo test --locked --manifest-path terminal/Cargo.toml
cargo clippy --locked --manifest-path terminal/Cargo.toml --all-targets -- -D warnings
```

Les tests Python n'ont besoin ni du cluster ni de Rust. Les tests Rust vérifient
contrat, clavier, vues vides, redimensionnements, requêtes obsolètes, préférences
et actions locales. La CI compile/teste sous Windows et Linux, dont Rust 1.88.
Sous Linux, `python tools/check_terminal_session.py --binary
terminal/target/release/romeo-tui` vérifie de vraies sessions PTY : navigation,
`q`/Ctrl-C, reconnexion après arrêt du lecteur, délai d'un lecteur bloqué,
restauration du terminal et absence de lecteur restant. Il inspecte aussi les
séquences ANSI des trois modes couleur, avec et sans `NO_COLOR`.
