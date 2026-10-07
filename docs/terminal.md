# Tableau de bord terminal (version interne 0.2)

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

Le mode `--demo` affiche des jobs, transferts, checkpoints, rapports et versions **fictifs**. Il ne
lit ni votre registre ni votre configuration et n'utilise aucun accès ROMEO.
Sans cette option, le tableau présente les traces locales de cette installation.

La commande courte `romeo-mcp tui` fonctionne aussi lorsque cette version du
paquet est installée. Le wheel Python reste indépendant de Rust et ne contient
pas de binaire natif : compiler celui-ci depuis le dépôt ou une archive source,
puis passer `--binary CHEMIN` à la commande. `ROMEO_TUI_BINARY` accepte également
un chemin explicite ; un binaire `romeo-tui` présent dans `PATH` peut être utilisé.
Le binaire compilé dans le dépôt est choisi en priorité, après le chemin explicite.
Relancer `--build` après une modification des sources Rust. Le lecteur et le
binaire doivent utiliser le même contrat : cette version utilise le schéma 2.
Une incompatibilité est signalée dans les alertes ; recompiler puis relancer.

## Navigation

| Touche | Action |
|---|---|
| `1` à `5`, `Tab`, Maj-Tab, `←` / `→` | Choisir Aperçu, Jobs, Transferts, Mises à jour ou Rapports |
| `↑` / `↓`, `j` / `k`, Début / Fin | Sélectionner une ligne ; faire défiler l'aperçu, les mises à jour ou un panneau ouvert |
| Page précédente / suivante | Parcourir la liste par pages ou faire défiler le panneau ouvert |
| `/` | Saisir un filtre propre à Jobs, Transferts ou Rapports ; le premier caractère remplace le précédent filtre |
| Entrée | Conserver le filtre pendant sa saisie ; sinon ouvrir le détail complet d'une ligne ou de l'aperçu |
| Échap | Fermer un panneau ; dans une liste, effacer le filtre et quitter sa saisie en une seule fois |
| `r` | Relire les fichiers locaux, même en pause ; reconnecter un lecteur interrompu |
| `p` | Suspendre/reprendre la relecture automatique |
| `?` | Ouvrir/fermer l'aide |
| `!` | Lire le détail des erreurs et avertissements locaux |
| `q`, Ctrl-C | Quitter et restaurer le terminal |

Le terminal s'adapte à sa taille ; un format de 100 colonnes sur 30 lignes
est confortable. En dessous de 48 × 16, un message invite à l'agrandir.
Le mode compact réserve l'espace à la liste ; Entrée ouvre un détail défilant.
L'aide, l'aperçu, les mises à jour et les détails restent consultables en entier.
Une lecture lente n'empêche pas de naviguer ou de quitter. Après 10 secondes sans
réponse, le lecteur détenu par le tableau est arrêté et les dernières données
restent affichées. `r` relance ce lecteur ; il ne relance aucune opération ROMEO.

## Ce que montrent les vues

- **Aperçu** : calculs interrompus, résultats à valider et observations anciennes
  en premier, puis activité récente, profil et configuration. Les compteurs
  concernent les traces chargées, pas l'ensemble du cluster.
- **Jobs** : soumissions du registre, dernière observation Slurm enregistrée,
  son âge, durées et code de sortie connus. La disponibilité d'un service ne
  remplace pas l'observation Slurm du job. Un job `COMPLETED` garde un résultat
  « non validé » tant qu'une validation distincte n'a pas été enregistrée. Les
  champs durée écoulée, temps restant et code de sortie sont séparés ; `—`
  signifie qu'aucune valeur n'est connue. Les checkpoints affichés proviennent
  des observations du runtime, associées au job, à l'exécution, aux empreintes
  et aux rangs : génération, étape, intégrité, reprise et signaux enregistrés.
  L'âge reste celui de cette observation, même après une nouvelle lecture locale.
- **Transferts** : plans et états des workers, phase, âge du dernier signal
  de vie enregistré et validation de la copie. Un statut ancien ne prouve
  pas qu'un processus est encore actif ; une demande d'annulation ne prouve
  pas son arrêt. Les plans altérés ou observations d'un autre transfert
  sont écartés. La progression vient des mesures enregistrées, jamais du temps
  écoulé : octets utiles traités, pourcentage, débit et estimation de temps quand
  disponibles. Une copie à 100 % peut encore avoir un résultat non vérifié.
- **Mises à jour** : version du lecteur, sélection au prochain lancement,
  dernier contrôle GitHub en cache, autorisation et phase enregistrées.
  Un cache absent ou en erreur donne une disponibilité inconnue.
- **Rapports** : autorisation automatique effective, rapports locaux, état de
  publication, nombre d'occurrences et lien GitHub déjà enregistré. Une
  publication vérifiée reste une preuve datée ; la vue ne contrôle pas à
  nouveau l'issue et ne collecte ni jeton, description complète ou journal.

Les nouveaux transferts détachés utilisent `rsync --info=progress2` si le rsync
local est en version 3.1 ou supérieure. Un inventaire initial complet permet
un pourcentage global stable ; il peut coûter davantage de mémoire sur un
répertoire très volumineux. Le pourcentage arrondi fourni par rsync n'est pas
converti en une taille totale prétendument exacte. Sans ces mesures (scp,
ancien rsync ou ancien statut), la progression est indiquée comme non mesurée.
Ces statistiques sont sauvegardées par le worker, sans interrogation SSH
supplémentaire. Les transferts synchrones conservent leur comportement.

**La relecture du tableau est locale.** Elle n'interroge pas SSH, Slurm, Spack
ou GitHub, ne modifie pas la configuration et ne lance aucune opération.
Pour actualiser les observations du cluster, demander à l'assistant d'utiliser
les outils MCP appropriés ; le tableau relira ensuite leurs nouvelles traces.
La cible SSH actuelle n'est pas comparée aux cibles des anciennes observations :
les états sont présentés comme un historique, jamais comme un état courant.
Les mises à jour affichées appartiennent à l'installation qui lance le tableau ;
elles ne constituent pas un inventaire des autres installations MCP du poste.

Par défaut, le tableau charge les 40 dernières soumissions, jusqu'à 40 dossiers
de transfert récents et 40 rapports, puis relit les fichiers toutes les 5 secondes.
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

Le lecteur Python (`terminal_data.py`, `terminal_evidence.py`) définit les sources
et les preuves compactes. `transfer_progress.py` extrait les mesures numériques
des journaux rsync par blocs bornés ; aucun texte du journal n'est exporté.
Le lanceur (`terminal.py`) gère les options et la compilation explicite.
`terminal/src/model.rs`, `app.rs`, `ui/` et `bridge.rs` séparent contrat,
navigation, vues et lecteur en arrière-plan. Un seul processus Python est
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
vérifie la navigation, les sorties par `q` et Ctrl-C, la reconnexion après
arrêt du lecteur, le délai d'une lecture bloquée, la restauration des attributs
du terminal et l'absence de lecteur Python restant après fermeture.
