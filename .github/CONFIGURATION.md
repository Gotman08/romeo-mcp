# Configuration GitHub

[Accueil](../README.md) › [Documentation](../docs/README.md) › GitHub

Ce dossier contient la configuration des vérifications exécutées sur GitHub
lorsqu’une modification est poussée ou proposée dans une pull request.

## Contenu

| Section | Rôle |
|---|---|
| [Workflows](workflows/README.md) | Déroulement de la CI, environnements testés et lecture des échecs |
| [ci.yml](workflows/ci.yml) | Définition du workflow `Verifications` |

## Où lire les résultats ?

L’onglet [Actions du dépôt](https://github.com/Gotman08/romeo-mcp/actions)
conserve les exécutions et les journaux de chaque étape. Pour vérifier une
modification, choisir l’exécution correspondant à son commit.

La CI couvre les contrôles hors ligne et la construction du paquet. Les
[essais sur ROMEO](../tests/README.md#essais-sur-romeo) sont exécutés séparément
sur un compte autorisé et ne font pas partie de ce workflow.

## Contribuer

Avant de pousser, suivre les [vérifications locales](../CONTRIBUTING.md#avant-un-commit).
Un problème de sécurité se signale selon [SECURITY.md](../SECURITY.md), avec
des informations permettant sa reproduction sans publier de données privées.
