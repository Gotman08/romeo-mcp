# Contrôles Git locaux

[Accueil](../README.md) › [Contribution](../CONTRIBUTING.md) › Hooks Git

Ces hooks facultatifs exécutent le contrôle de confidentialité avant qu’un
commit ou un push soit finalisé sur votre poste.

<details>
<summary>Sommaire de cette page</summary>

- [Activer les hooks](#activer-les-hooks)
- [Contrôles exécutés](#contrôles-exécutés)
- [En cas de signalement](#en-cas-de-signalement)

</details>

## Activer les hooks

Depuis un clone Git du projet :

```sh
git config --local core.hooksPath .githooks
```

Ce réglage s’applique au clone courant. Chaque contributeur l’active dans
son propre clone ; il n’est pas transmis par un commit.

## Contrôles exécutés

| Hook | Commande | Périmètre |
|---|---|---|
| [pre-commit](pre-commit) | `python tools/check_privacy.py --staged` | Contenus de l’index et identité du prochain commit |
| [pre-push](pre-push) | `python tools/check_privacy.py --history` | Contenus et métadonnées accessibles dans l’historique local |

Le hook cherche d’abord le Python du venv du dépôt, puis `python3` ou `python`
dans le `PATH`. Un code de sortie non nul bloque l’opération Git concernée.

## En cas de signalement

Lire le fichier et la ligne indiqués, corriger les données préparées ou
l’identité Git, puis relancer le contrôle. Modifier uniquement la copie de
travail ne change pas un fichier déjà présent dans l’index : les corrections
doivent être préparées à nouveau avec `git add`.

Un secret déjà diffusé exige également la procédure décrite dans
[SECURITY.md](../SECURITY.md). Pour comprendre les motifs détectés et leurs
limites, consulter les [utilitaires de confidentialité](../tools/README.md#vérifier-avant-de-publier).
La [CI](../.github/workflows/README.md) répète le contrôle sur GitHub.

---

[↑ Haut de page](#contrôles-git-locaux) · [Accueil](../README.md) · [Documentation](../docs/README.md) · [Catalogue Tools](../docs/Tools.md)
