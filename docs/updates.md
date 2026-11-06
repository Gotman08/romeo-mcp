# Mettre à jour ROMEO MCP

[Accueil](../README.md) › [Documentation](README.md) › Mises à jour

Le CLI installe les releases stables du
[dépôt officiel](https://github.com/Gotman08/romeo-mcp/releases). **L’installation se
décide hors du modèle** : les outils MCP lisent seulement l’état des versions, et
chaque wheel doit présenter une attestation Sigstore valide avant toute installation.

<details>
<summary>Sommaire de cette page</summary>

- [Les trois commandes](#les-trois-commandes)
- [Ce que le modèle peut faire](#ce-que-le-modèle-peut-faire)
- [Ce qui se passe après votre accord](#ce-qui-se-passe-après-votre-accord)
- [Ce que la vérification garantit](#ce-que-la-vérification-garantit)
- [Revenir à la version précédente](#revenir-à-la-version-précédente)
- [Détection automatique et réseau](#détection-automatique-et-réseau)
- [Où sont conservées les versions ?](#où-sont-conservées-les-versions-)
- [Activer le système sur une ancienne installation](#activer-le-système-sur-une-ancienne-installation)
- [Publier une nouvelle version](#publier-une-nouvelle-version)

</details>

## Les trois commandes

Utiliser le Python de l’installation enregistrée dans votre client. Si le venv
est activé, les commandes sont :

```sh
python -m romeo_mcp update --check
python -m romeo_mcp update
python -m romeo_mcp update --rollback
python -m romeo_mcp update --auto on
```

Le raccourci `romeo-mcp update` fonctionne aussi avec le venv activé. Sans
activation, remplacer `python` par `.venv\Scripts\python.exe` sous Windows,
ou `.venv/bin/python` sous Linux et WSL, depuis la racine de votre installation.
Chaque installation possède son propre historique de mises à jour.

| Commande | Effet |
|---|---|
| `update --check` | Affiche les versions actuelle et disponible, sans installation |
| `update --check --json` | Fournit ces informations sous forme structurée |
| `update` | Affiche les notes, demande confirmation et prépare la dernière release stable |
| `update --rollback` | Vérifie puis sélectionne l’environnement précédent |
| `update --yes` | Installe avec confirmation explicite déjà donnée, sans dialogue interactif |
| `update --rollback --yes` | Confirme explicitement le retour arrière |
| `update --auto on` | Autorise l’installation automatique des releases attestées au démarrage ; exige un terminal interactif |
| `update --auto off` | Retire cet accord |

Dans un terminal non interactif, la commande d’installation refuse d’avancer
sans `--yes`. `update --auto on` refuse tout terminal non interactif, même avec
`--yes`. Le serveur ne pose aucune question sur son canal MCP stdio.

## Ce que le modèle peut faire

Deux outils en lecture seule sont disponibles dans les profils `essential`, `full`
et `expert` :

| Outil | Rôle |
|---|---|
| [`mcp_update_check`](tools/mcp_update_check.md) | Détecter une release, présenter ses notes et distinguer version exécutée et version sélectionnée |
| [`mcp_update_status`](tools/mcp_update_status.md) | Relire la progression et le résultat, y compris après reconnexion |

Aucun outil MCP n’installe une version, ne revient en arrière ni ne modifie l’accord
automatique. Une instruction injectée dans le contexte du modèle, par exemple
depuis des notes de release ou un journal, ne peut donc pas déclencher une
installation par ces outils. Les instructions MCP demandent seulement au modèle de
signaler une nouvelle version et de renvoyer vers le terminal.

Le serveur en cours continue avec `running_version`, et la version préparée est
`next_start_version` : **reconnecter le MCP ou redémarrer l’application** quand
`restart_required=true`, puis vérifier la version réellement exécutée.

Seules les releases stables officielles sont installables. Un commit poussé sur
une branche, une prerelease ou une version sans wheel, sans SHA-256 ou sans
attestation ne constitue pas une mise à jour installable.

## Ce qui se passe après votre accord

1. Le CLI vérifie que le clone d’origine est propre et pointe vers le dépôt
   officiel. Un fichier modifié ou non suivi bloque l’installation.
2. Il télécharge la wheel de la release stable et compare sa taille et son
   empreinte SHA-256 à celles annoncées par GitHub.
3. Il récupère les attestations de cette empreinte et les vérifie dans un venv
   dédié, avec la racine de confiance Sigstore. L’attestation doit être une
   provenance SLSA signée par le workflow de release du dépôt officiel, exécuté
   depuis le tag de cette version. Sans cela, rien n’est installé.
4. Il crée un venv séparé, installe les dépendances du verrou contenu dans la wheel
   avec `pip --require-hashes --no-deps --only-binary :all:`, puis la wheel sans
   index. Il vérifie enfin l’import du serveur et les empreintes de la documentation.
5. Si ces vérifications réussissent, il enregistre la version à utiliser lors
   du prochain démarrage. Une interruption avant cette sélection conserve la
   version active. Les installations simultanées sont verrouillées.
6. **Reconnecter le MCP dans le client**, ou redémarrer ce client, pour charger
   la nouvelle version. `python -m romeo_mcp --version` indique la version
   choisie pour un nouveau processus.

Un serveur déjà ouvert conserve son environnement et peut terminer un transfert
ou un appel. Les jobs soumis sur ROMEO restent gérés par Slurm. Le lanceur
d’origine doit rester présent à son emplacement : il dirige les prochains
démarrages vers la version préparée. Les fichiers du checkout restent en place ;
la version réellement exécutée peut donc être plus récente que ce checkout.

Les paramètres personnels, clés SSH, rapports et registre local des jobs ne
sont pas remplacés par l’installateur.

## Ce que la vérification garantit

| Élément | Protection |
|---|---|
| Wheel | L’attestation lie son empreinte au workflow `.github/workflows/ci.yml` du dépôt, sur le tag `vX.Y.Z`. Une wheel remplacée ou un SHA-256 falsifié par l’API GitHub est refusé |
| Dépendances | Le verrou fait partie de la wheel attestée. Chaque paquet doit correspondre à une empreinte figée, sans résolution ni code de construction |
| Vérificateur | Sigstore tourne dans un venv dédié, lui-même épinglé par hash, hors du serveur MCP |

Limites à connaître :

- Une attestation prouve l’origine de la construction, pas l’innocence du code. Un
  compte mainteneur compromis capable de pousser un tag peut encore produire une
  release attestée. Elle reste alors inscrite au journal public Sigstore. Protéger
  les tags et la branche `main`, et exiger une validation sur le workflow de release,
  réduit ce risque.
- Une installation antérieure à cette version ne connaît pas encore cette
  vérification : sa première mise à jour se fait avec l’ancien contrôle SHA-256.
- `python -m pip install -e .` résout les dépendances au moment de l’installation
  initiale. Pour les figer aussi, installer d’abord le verrou :
  `python -m pip install --require-hashes --no-deps --only-binary :all: -r romeo_mcp/locks/server.lock`.

## Revenir à la version précédente

Après `update --rollback`, reconnecter le client de la même façon. Le retour
arrière échange la version sélectionnée et la version précédente ; une seconde
commande permet de revenir sur celle que vous venez de quitter.

Si l’accord automatique est actif, la version annulée et les versions inférieures
sont écartées automatiquement. Une release plus récente reste éligible. Un nouvel
`update --auto on` efface cet écartement ; une installation manuelle reste possible.

Si une version préparée ne démarre plus, lancer la commande avec le Python
**d’origine**. L’option `--rollback` reste traitée par ce lanceur. Si des fichiers
de l’installation d’origine ont été modifiés depuis la première mise à jour,
le retour vers cette installation est refusé. Un diagnostic qui échoue conserve
la sélection courante et affiche la cause.

Le retour arrière concerne le code, ses dépendances et son corpus. Il ne remet
pas à une date antérieure vos paramètres, votre registre ni vos données de
calcul. Les futures notes de version devront préciser toute migration de ces
données et sa compatibilité avec les versions précédentes.

## Détection automatique et réseau

Au démarrage du serveur, une tâche en arrière-plan peut interroger GitHub.
Le résultat réussi est gardé pendant 24 heures ; une erreur réseau est conservée
cinq minutes, puis peut être réessayée. Les outils rendent l'âge du contrôle.
Une erreur donne `ok=false` et `update_available=null` : la disponibilité est
inconnue, elle ne signifie pas qu'il n'existe aucune mise à jour.
`mcp_update_check(refresh=true)` et `update --check` forcent un nouveau contrôle.
Une préparation automatique qui échoue attend cinq minutes avant une nouvelle
tentative au démarrage suivant. Le serveur reste utilisable pendant ces étapes.

L’installation automatique reste désactivée tant que vous ne lancez pas
`update --auto on` dans un terminal. Elle applique la même vérification qu’une
installation manuelle. `ROMEO_AUTO_UPDATE=1` l’autorise dans l’environnement du
serveur et `ROMEO_AUTO_UPDATE=0` la désactive même si un accord est enregistré. Les
résultats exposent cette priorité avec `policy_source`. Un accord enregistré par une
version antérieure, qui pouvait venir du modèle, n’est pas repris : `policy_source`
vaut alors `legacy_ignored`.

Pour désactiver cette détection, ajouter `ROMEO_UPDATE_CHECK=0` à l’environnement
du serveur dans votre client. Les commandes manuelles restent disponibles.
Aucun jeton GitHub n’est nécessaire pour ce dépôt public. Une panne réseau
n’empêche pas le serveur de démarrer ; elle empêche seulement la vérification
ou l’installation d’une nouvelle version.

## Où sont conservées les versions ?

| Système | Répertoire par défaut |
|---|---|
| Windows | `%LOCALAPPDATA%\romeo-mcp\updates\` |
| Linux et WSL | `$XDG_DATA_HOME/romeo-mcp/updates/`, sinon `~/.local/share/romeo-mcp/updates/` |

Un sous-dossier identifie chaque couple Python/installation d’origine. Il
contient les venv, le vérificateur d’attestations, les wheels, les métadonnées de
release, un cache de contrôle, la politique automatique, les plans et observations
des workers, et le fichier de sélection. `ROMEO_UPDATES_DIR` permet de choisir une autre
racine **hors de tout dépôt Git** ; conserver la même valeur dans le terminal
et dans le client. Déplacer le lanceur ou changer cette valeur crée un autre
contexte de mise à jour. Les venv Python préparés doivent être recréés après
un déplacement, pas déplacés à la main.

Les anciennes versions restent sur disque pour permettre le retour arrière
et protéger les processus encore actifs. Il n’y a pas de nettoyage automatique.
Pour libérer de la place, arrêter tous les processus concernés et conserver
les dossiers désignés par `active` et `previous` dans `state.json`.

## Activer le système sur une ancienne installation

Les versions antérieures à 1.4.0 nécessitent une première actualisation manuelle.
Fermer leur serveur MCP, puis, depuis un clone propre avec son venv activé :

```sh
git pull --ff-only
python -m pip install -e .
python -m romeo_mcp --version
python -m romeo_mcp update --check
```

Reconnecter ensuite le client. Une installation issue d’une wheel s’actualise
une première fois en installant la wheel 1.4.0 de la release avec son Python.
Les commandes `update` deviennent ensuite disponibles pour les versions suivantes.

## Publier une nouvelle version

Pour les mainteneurs :

1. Incrémenter la version dans `pyproject.toml` et `romeo_mcp/__init__.py`.
2. Ajouter une section `## X.Y.Z` dans [CHANGELOG.md](../CHANGELOG.md), puis actualiser
   les verrous avec `python tools/lock_dependencies.py` si les dépendances changent.
3. Lancer les [tests](../tests/README.md), construire le paquet avec
   `python -m build`, puis vérifier `python tools/prepare_release.py --tag vX.Y.Z`.
4. Commiter et pousser sur `main`. Attendre la réussite de la CI.
5. Créer un tag annoté `vX.Y.Z` sur ce commit et le pousser.

Le [workflow](../.github/workflows/README.md) rejoue les tests sur quatre
combinaisons Windows/Linux et Python. Il atteste la wheel, les sources et
`SHA256SUMS`, prépare une release en brouillon, les charge, puis publie la release.
Un simple push sur `main` ne déclenche aucune installation chez les utilisateurs.
Une release publiée est conservée telle quelle : une correction reçoit une
nouvelle version et un nouveau tag.

---

[↑ Haut de page](#mettre-à-jour-romeo-mcp) · [Accueil](../README.md) · [Documentation](README.md) · [Catalogue Tools](Tools.md)
