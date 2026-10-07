# Tableau de bord terminal (version interne)

[Accueil](../README.md) · [Documentation](README.md)

Cette interface facultative utilise [Ratatui](https://ratatui.rs/) et s'ouvre
uniquement sur demande. Le lancement habituel de `romeo-mcp` reste le serveur
MCP en stdio. Il ne lance pas d'interface et ne requiert ni Rust ni Cargo.

## Premier essai depuis le dépôt

Installer [Rust avec rustup](https://rustup.rs/) (Rust 1.88 ou supérieur).
Sous Windows, la compilation nécessite aussi les outils C++ de Visual Studio
et le SDK Windows ; sous Linux, un compilateur/linker C, par exemple `cc`.
Python 3.11 ou supérieur est nécessaire pour le lecteur des données.

Dans le dossier du dépôt :

```console
python -m romeo_mcp tui --build --demo
```

`--build` compile explicitement le binaire avec les dépendances verrouillées
dans `terminal/Cargo.lock`. Cargo télécharge les dépendances manquantes à ce
moment-là seulement. Les lancements suivants réutilisent le binaire :

```console
python -m romeo_mcp tui --demo
python -m romeo_mcp tui
```

Le mode `--demo` affiche des jobs, transferts et versions **fictifs**. Il ne
lit ni votre registre ni votre configuration et n'utilise aucun accès ROMEO.
Sans cette option, le tableau présente les traces locales de cette installation.

La commande courte `romeo-mcp tui` fonctionne aussi lorsque cette version du
paquet est installée. Le wheel Python reste indépendant de Rust et ne contient
pas de binaire natif : compiler celui-ci depuis le dépôt ou une archive source,
puis passer `--binary CHEMIN` à la commande. `ROMEO_TUI_BINARY` accepte également
un chemin explicite ; un binaire `romeo-tui` présent dans `PATH` peut être utilisé.
Le binaire compilé dans le dépôt est choisi en priorité, après le chemin explicite.
Relancer `--build` après une modification des sources Rust.

## Navigation

| Touche | Action |
|---|---|
| `1` à `4`, `Tab`, `←` / `→` | Choisir Aperçu, Jobs, Transferts ou Mises à jour |
| `↑` / `↓`, `j` / `k`, Début / Fin | Sélectionner une ligne et lire son détail |
| `/` | Filtrer noms, identifiants et états dans Jobs ou Transferts |
| Entrée | Fermer la saisie du filtre |
| Échap | Fermer l'aide/la saisie ; sinon effacer le filtre |
| `r` | Relire les fichiers locaux, même lorsque la relecture est en pause |
| `p` | Suspendre/reprendre la relecture automatique |
| `?` | Ouvrir/fermer l'aide |
| `q`, Ctrl-C | Quitter et restaurer le terminal |

Le terminal s'adapte à sa taille ; un format de 100 colonnes sur 30 lignes
est confortable. En dessous de 48 × 16, un message invite à l'agrandir.
Une lecture lente des fichiers n'empêche pas de naviguer ou de quitter.

## Ce que montrent les vues

- **Aperçu** : profil, configuration présente et nombres de traces chargées.
- **Jobs** : soumissions du registre, dernière observation Slurm enregistrée,
  son âge, durées et code de sortie connus. La disponibilité d'un service ne
  remplace pas l'observation Slurm du job. Un job `COMPLETED` garde un résultat
  « non validé » tant qu'une validation distincte n'a pas été enregistrée.
- **Transferts** : plans et états des workers, phase, âge du dernier signal
  de vie enregistré et validation de la copie. Un statut ancien ne prouve
  pas qu'un processus est encore actif ; une demande d'annulation ne prouve
  pas son arrêt. Les plans altérés ou observations d'un autre transfert
  sont écartés.
- **Mises à jour** : version du lecteur, sélection au prochain lancement,
  dernier contrôle GitHub en cache, autorisation et phase enregistrées.
  Un cache absent ou en erreur donne une disponibilité inconnue.

**La relecture du tableau est locale.** Elle n'interroge pas SSH, Slurm, Spack
ou GitHub, ne modifie pas la configuration et ne lance aucune opération.
Pour actualiser les observations du cluster, demander à l'assistant d'utiliser
les outils MCP appropriés ; le tableau relira ensuite leurs nouvelles traces.
La cible SSH actuelle n'est pas comparée aux cibles des anciennes observations :
les états sont présentés comme un historique, jamais comme un état courant.
Les mises à jour affichées appartiennent à l'installation qui lance le tableau ;
elles ne constituent pas un inventaire des autres installations MCP du poste.

Par défaut, le tableau charge les 40 dernières soumissions et jusqu'à 40 dossiers
de transfert récents, puis relit les fichiers toutes les 5 secondes.
`--limit` accepte 1 à 100 et `--refresh` 1 à 300 secondes.
L'inventaire parcourt au maximum 1 000 entrées de transfert ; une limite atteinte
est signalée. Les entrées JSON et observations sont bornées ; une source
illisible produit un avertissement au lieu d'un faux résultat réussi.
Le registre n'est pas créé par l'interface. `ROMEO_MCP_DB` ou `--db CHEMIN`
permettent d'en choisir un autre, ouvert en lecture seule.

Les clés SSH, noms d'utilisateur, codes projet, scripts et jetons ne font pas
partie du contrat d'affichage. Les noms de jobs et chemins de transfert peuvent
contenir des informations privées : utiliser `--demo` pour une capture publique.
Les caractères de contrôle des données sont neutralisés avant affichage.

## Rendu sans terminal et développement

```console
python -m romeo_mcp tui --demo --snapshot --view jobs --width 100 --height 30
python -m romeo_mcp tui --demo --json
```

`--snapshot` utilise réellement le backend de test Ratatui pour produire un
rendu texte. `--json` fournit le relevé versionné sans nécessiter le binaire Rust.
Un lancement interactif avec des flux redirigés est refusé avant d'activer le
mode brut du terminal. Aucune sortie de tableau n'est ajoutée au protocole MCP.

Le lecteur Python (`terminal_data.py`) définit les sources et la confidentialité.
Le lanceur (`terminal.py`) gère les options et la compilation explicite.
`terminal/src/model.rs`, `app.rs`, `ui.rs` et `bridge.rs` séparent contrat,
navigation, rendu et lecteur en arrière-plan. Un seul processus Python est
utilisé, avec des canaux bornés ; il est arrêté à la fermeture du tableau.

```console
python tests/run_all.py --only terminal
cargo fmt --manifest-path terminal/Cargo.toml -- --check
cargo test --locked --manifest-path terminal/Cargo.toml
cargo clippy --locked --manifest-path terminal/Cargo.toml --all-targets -- -D warnings
```

Les tests Python n'ont besoin ni du cluster ni de Rust. Les tests Rust vérifient
le contrat, le clavier, les vues vides et les redimensionnements. La CI compile
et teste également l'interface sous Windows et Linux, ainsi qu'avec Rust 1.88.
Sous Linux, `python tools/check_terminal_session.py --binary
terminal/target/release/romeo-tui` ouvre deux sessions PTY de démonstration et
vérifie la navigation, les sorties par `q` et Ctrl-C, la restauration des
attributs du terminal et l'arrêt du lecteur Python.
