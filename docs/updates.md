# Mettre à jour ROMEO MCP

[Accueil](../README.md) › [Documentation](README.md) › Mises à jour

À partir de la version 1.4.0, le CLI peut installer les releases stables du
[dépôt officiel](https://github.com/Gotman08/romeo-mcp/releases). Le modèle peut
maintenant les contrôler et les préparer avec les outils MCP. **Un accord
automatique enregistré une fois suffit pour les versions suivantes.**

<details>
<summary>Sommaire de cette page</summary>

- [Les trois commandes](#les-trois-commandes)
- [Mise à jour par le modèle](#mise-à-jour-par-le-modèle)
- [Ce qui se passe après votre accord](#ce-qui-se-passe-après-votre-accord)
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
sans `--yes`. Le terminal conserve cette confirmation ; les outils MCP utilisent
`confirm=true`, après un accord ponctuel ou un accord automatique déjà donné.
Le serveur ne pose aucune question sur son canal MCP stdio.

## Mise à jour par le modèle

Les cinq outils sont disponibles dans les profils `essential`, `full` et `expert` :

| Outil | Rôle |
|---|---|
| [`mcp_update_check`](tools/mcp_update_check.md) | Détecter une release, présenter ses notes et distinguer version exécutée et version sélectionnée |
| [`mcp_update_policy`](tools/mcp_update_policy.md) | Enregistrer durablement l'autorisation automatique ou la désactiver |
| [`mcp_update_start`](tools/mcp_update_start.md) | Préparer la release dans un processus séparé, sans bloquer les autres outils |
| [`mcp_update_status`](tools/mcp_update_status.md) | Relire la progression et le résultat, y compris après reconnexion |
| [`mcp_update_rollback`](tools/mcp_update_rollback.md) | Vérifier et sélectionner l'environnement précédent |

Après une demande comme « autorise les mises à jour automatiques », le modèle
enregistre `mcp_update_policy(automatic=true, confirm=true)`. Il appelle
`mcp_update_check`, annonce la version disponible et lance
`mcp_update_start(confirm=true, expected_version=latest_version)`. L'accord
reste enregistré hors Git pour cette installation : il ne doit pas le
redemander à chaque release. Pour l'annuler, utiliser la même politique avec
`automatic=false` ; une préparation déjà démarrée peut encore se terminer.

Au démarrage du serveur, l'accord automatique permet également de préparer
une nouvelle release sans attendre un appel du modèle. Les instructions MCP
demandent au modèle de lire `mcp_update_check` au début de chaque session et
de signaler nouvelle version, échec, préparation ou reconnexion nécessaire.
Un client doit transmettre ces instructions et résultats à son modèle pour
que l'annonce soit visible ; l'installation automatique ne dépend pas de sa
capacité à afficher `stderr`.

`started=true` signifie seulement que le worker a été lancé. Le modèle suit
`mcp_update_status` jusqu'à `operation.state="ready"` et
`operation.result_validated=true`. Les phases sont téléchargement, création
du venv, installation, vérification et sélection. Les observations sont
horodatées. Un verrou détenu indique une transaction, sans certifier le PID ;
une observation ancienne sans verrou devient `interrupted`. Une nouvelle
tentative crée un candidat neuf et laisse la version sélectionnée en place.

La version préparée est `next_start_version`. Le serveur en cours continue
avec `running_version` : **reconnecter le MCP ou redémarrer l'application**
quand `restart_required=true`, puis vérifier la version réellement exécutée.
Une demande répétée ne réinstalle pas une version déjà sélectionnée et ne
lance pas un deuxième worker pour une préparation en cours.

Les outils utilisent uniquement les releases stables officielles. Un commit
poussé sur une branche, une prerelease ou une version dont la wheel ou le
SHA-256 manque ne constitue pas une mise à jour installable.

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

Le modèle peut effectuer ce parcours avec `mcp_update_rollback(confirm=true)`
et `mcp_update_status`. Si l'automatisme est activé, la version annulée et les
versions inférieures sont écartées automatiquement. Une release plus récente
reste éligible. Une nouvelle autorisation avec `mcp_update_policy` efface cet
écartement ; une installation manuelle reste possible.

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

`ROMEO_AUTO_UPDATE=1` peut autoriser l'installation automatique dans
l'environnement du serveur ; `ROMEO_AUTO_UPDATE=0` la désactive même si un accord
est enregistré. Les résultats exposent cette priorité avec `policy_source`.
Sans variable et sans accord enregistré, seule la détection est automatique.

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
contient les venv, les wheels, les métadonnées de release, un cache de contrôle,
la politique automatique, les plans et observations des workers, et le fichier
de sélection. `ROMEO_UPDATES_DIR` permet de choisir une autre
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

---

[↑ Haut de page](#mettre-à-jour-romeo-mcp) · [Accueil](../README.md) · [Documentation](README.md) · [Catalogue Tools](Tools.md)
