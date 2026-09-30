# Vérifications automatiques

[Accueil](../../README.md) › [GitHub](../CONFIGURATION.md) › Workflows

[ci.yml](ci.yml) définit le workflow `Verifications`. Il démarre lors d’un
push, d’une pull request ou d’un lancement manuel via GitHub Actions.

<details>
<summary>Sommaire de cette page</summary>

- [Environnements couverts](#environnements-couverts)
- [Étapes du workflow](#étapes-du-workflow)
- [Publication des releases](#publication-des-releases)
- [Lire un échec](#lire-un-échec)

</details>

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
4. Exécuter les neuf [suites hors ligne](../../tests/README.md#suites-hors-ligne).
5. Construire les distributions Python avec `python -m build`.

Le job de test dispose de `contents: read`. Aucun accès SSH ROMEO n’est
nécessaire.

## Publication des releases

Un tag stable `vX.Y.Z` ajoute le job `release`, après la réussite des quatre
combinaisons de tests. Ce job dispose seul de `contents: write`. Il construit
les distributions et vérifie leur cohérence avec les versions du code et le
changelog grâce à [prepare_release.py](../../tools/prepare_release.py).

La release est créée en brouillon. La wheel, l’archive source et `SHA256SUMS`
sont chargés avant sa publication. Si cette étape échoue, le brouillon peut
rester présent ; le terminer après vérification ou le retirer avant de relancer
le job. Ne pas remplacer une release déjà publiée : incrémenter sa version.

Les pushes ordinaires et les pull requests exécutent les tests sans publier.
Voir le [guide de maintenance](../../docs/updates.md#publier-une-nouvelle-version).

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

---

[↑ Haut de page](#vérifications-automatiques) · [Accueil](../../README.md) · [Documentation](../../docs/README.md) · [Catalogue Tools](../../docs/Tools.md)
