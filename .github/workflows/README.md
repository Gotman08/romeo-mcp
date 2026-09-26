# Vérifications automatiques

[Accueil](../../README.md) › [GitHub](../README.md) › Workflows

[ci.yml](ci.yml) définit le workflow `Verifications`. Il démarre lors d’un
push, d’une pull request ou d’un lancement manuel via GitHub Actions.

## Environnements couverts

| Système | Versions Python |
|---|---|
| Ubuntu, image `ubuntu-latest` | 3.11 et 3.13 |
| Windows, image `windows-latest` | 3.11 et 3.13 |

Les quatre combinaisons s’exécutent indépendamment. La configuration laisse
les autres combinaisons terminer lorsqu’une première échoue.

## Étapes du workflow

1. Récupérer le dépôt avec son historique Git complet.
2. Installer le paquet, les dépendances documentaires et l’outil de construction.
3. Vérifier les fichiers et l’historique avec `check_privacy.py --history`.
4. Exécuter les huit [suites hors ligne](../../tests/README.md#suites-hors-ligne).
5. Construire les distributions Python avec `python -m build`.

Le jeton du workflow dispose de `contents: read`. Aucun accès SSH ROMEO n’est
nécessaire. Ce workflow produit une preuve de vérification ; il ne publie pas
automatiquement une version du paquet.

## Lire un échec

Dans [Actions](https://github.com/Gotman08/romeo-mcp/actions/workflows/ci.yml),
ouvrir le commit concerné, puis la combinaison système/Python en échec.

| Étape | Première piste |
|---|---|
| Installer | Versions Python, dépendances et métadonnées du paquet |
| Vérifier les fichiers et l’historique | Chemins signalés, contenu de l’index et identités des commits |
| Tester sans cluster | Nom de la suite en échec, puis cas et assertion correspondants |
| Construire les distributions | `pyproject.toml`, `MANIFEST.in` et fichiers à embarquer |

Reproduire la commande localement avec la même version de Python. Les
[utilitaires](../../tools/README.md) et le [guide des tests](../../tests/README.md)
donnent les commandes ciblées.
