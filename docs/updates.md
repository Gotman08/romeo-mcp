# Mettre à jour ROMEO MCP

[Accueil](../README.md) › [Documentation](README.md) › Mises à jour

À partir de la version 1.4.0, le CLI peut installer les releases stables du
[dépôt officiel](https://github.com/Gotman08/romeo-mcp/releases). La détection est
automatique ; **l’installation demande votre accord**.

## Les trois commandes

Utiliser le Python de l’installation enregistrée dans votre client. Si le venv
est activé, les commandes sont :

```sh
python -m romeo_mcp update --check
python -m romeo_mcp update
python -m romeo_mcp update --rollback
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

Dans un terminal non interactif, la commande d’installation refuse d’avancer
sans `--yes`. Un client IA peut consulter `--check --json`, présenter les notes
à l’utilisateur, puis lancer `update --yes` après son accord. Le serveur ne
pose aucune question sur son canal MCP stdio et n’expose pas d’outil MCP capable
de remplacer son propre code.

## Ce qui se passe après votre accord

1. Le CLI vérifie que le clone d’origine est propre et pointe vers le dépôt
   officiel. Un fichier modifié ou non suivi bloque l’installation.
2. Il télécharge la wheel de la release stable et compare sa taille et son
   empreinte SHA-256 à celles annoncées par GitHub.
3. Il crée un venv séparé, installe le paquet et ses dépendances, puis vérifie
   l’import du serveur et les empreintes de la documentation embarquée.
4. Si ces vérifications réussissent, il enregistre la version à utiliser lors
   du prochain démarrage. Une interruption avant cette sélection conserve la
   version active. Les installations simultanées sont verrouillées.
5. **Reconnecter le MCP dans le client**, ou redémarrer ce client, pour charger
   la nouvelle version. `python -m romeo_mcp --version` indique la version
   choisie pour un nouveau processus.

Un serveur déjà ouvert conserve son environnement et peut terminer un transfert
ou un appel. Les jobs soumis sur ROMEO restent gérés par Slurm. Le lanceur
d’origine doit rester présent à son emplacement : il dirige les prochains
démarrages vers la version préparée. Les fichiers du checkout restent en place ;
la version réellement exécutée peut donc être plus récente que ce checkout.

Les paramètres personnels, clés SSH, rapports et registre local des jobs ne
sont pas remplacés par l’installateur. Les dépendances Python sont obtenues
depuis l’index configuré pour `pip` ; elles ne sont pas incluses dans la wheel.
L’empreinte GitHub contrôle l’intégrité de cette wheel, sans constituer une
signature indépendante de GitHub.

## Revenir à la version précédente

Après `update --rollback`, reconnecter le client de la même façon. Le retour
arrière échange la version sélectionnée et la version précédente ; une seconde
commande permet de revenir sur celle que vous venez de quitter.

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
Le résultat est gardé pendant 24 heures, même en cas d’échec réseau, afin
d’éviter des tentatives répétées. La notification utilise uniquement `stderr` :
sa visibilité dépend du client. `update --check` effectue toujours une nouvelle
vérification et indique explicitement les erreurs de connexion ou de limite API.

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
contient les venv, les wheels, les métadonnées de release, un cache de contrôle
et le fichier de sélection. `ROMEO_UPDATES_DIR` permet de choisir une autre
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
2. Ajouter une section `## X.Y.Z` dans [CHANGELOG.md](../CHANGELOG.md).
3. Lancer les [tests](../tests/README.md), construire le paquet avec
   `python -m build`, puis vérifier `python tools/prepare_release.py --tag vX.Y.Z`.
4. Commiter et pousser sur `main`. Attendre la réussite de la CI.
5. Créer un tag annoté `vX.Y.Z` sur ce commit et le pousser.

Le [workflow](../.github/workflows/README.md) rejoue les tests sur quatre
combinaisons Windows/Linux et Python. Il prépare ensuite une release en
brouillon, charge la wheel, les sources et `SHA256SUMS`, puis publie la release.
Un simple push sur `main` ne déclenche aucune installation chez les utilisateurs.
Une release publiée est conservée telle quelle : une correction reçoit une
nouvelle version et un nouveau tag.
