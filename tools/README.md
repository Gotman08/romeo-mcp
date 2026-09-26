# Utilitaires du projet

[Accueil](../README.md) › [Documentation](../docs/README.md) › Utilitaires

Ces scripts accompagnent l’installation et la maintenance du dépôt. Ils se
lancent depuis la **racine du projet**, avec le Python du venv activé. Pour
soumettre un calcul, utiliser les [outils MCP](../docs/reference.md).

## Choisir le bon script

| Script | Usage | Effets |
|---|---|---|
| [install_mcp.py](install_mcp.py) | Enregistrer le serveur dans un client IA | Peut modifier les fichiers personnels du client, avec sauvegarde préalable |
| [check_privacy.py](check_privacy.py) | Vérifier les contenus qui seront publiés | Lit l’index Git et, sur demande, l’historique ; affiche les emplacements signalés |
| [verify_corpus.py](verify_corpus.py) | Contrôler la copie documentaire | Lit les liens, images, accès depuis le sommaire et empreintes du manifeste |
| [romeo_doc_scraper.py](romeo_doc_scraper.py) | Renouveler la copie du site ROMEO | Accède au site officiel et écrit dans le dossier de sortie choisi |

## Enregistrer le MCP dans un client

```sh
python tools/install_mcp.py --list
python tools/install_mcp.py --targets codex --dry-run
python tools/install_mcp.py --targets codex
```

Les cibles sont `codex`, `claude-code` et `claude-desktop`. Une liste séparée
par des virgules permet d’en choisir plusieurs. `--dry-run` montre les
changements prévus ; sans cette option, le script enregistre la configuration
et vérifie le démarrage du serveur. Le relancer met à jour la même entrée.

Le projet Slurm se règle séparément avec `python -m romeo_mcp configure`.
Les options `--python`, `--name` et les fichiers de configuration explicites
sont détaillés par `python tools/install_mcp.py --help`.
Voir aussi la [configuration des clients](../docs/configuration.md#autres-clients-stdio).

## Vérifier avant de publier

```sh
python tools/check_privacy.py --staged
python tools/check_privacy.py --history
python tools/verify_corpus.py
```

Le contrôle de confidentialité lit **l’index**, c’est-à-dire les fichiers
préparés avec `git add`. `--staged` vérifie aussi l’identité du prochain
commit ; `--history` parcourt les objets accessibles depuis les références Git.
Un signalement produit un code de sortie non nul et doit être examiné avant
publication. Ce contrôle cible des motifs connus.

Les [hooks locaux](../.githooks/README.md) et la
[CI GitHub](../.github/workflows/README.md) utilisent ces mêmes vérifications.

## Renouveler la documentation ROMEO

Installer les dépendances facultatives avec `python -m pip install -e ".[docs]"`,
puis choisir un dossier temporaire extérieur au dépôt :

```sh
python tools/romeo_doc_scraper.py --output CHEMIN_TEMPORAIRE
python tools/verify_corpus.py CHEMIN_TEMPORAIRE
```

Avant d’intégrer cette collecte :

1. Lire les erreurs et comparer les pages, les images et le sommaire à la copie versionnée.
2. Reprendre les README de navigation propres au projet et adapter leurs liens
   si les sections officielles ont changé. Le collecteur génère son propre
   README d’accueil ; il ne produit pas tous ces guides de section.
3. Actualiser les empreintes de `manifest.json` pour le corpus intégré, ainsi
   que l’inventaire `local_navigation` de ses README.
4. Vérifier les liens, le manifeste et la recherche locale avec les
   [suites documentaires](../tests/README.md#suites-hors-ligne).
5. Publier ensemble les pages, les images, la navigation et le manifeste.

La date de collecte décrit les pages officielles. La navigation ajoutée par
le projet reste identifiée séparément dans le [README du corpus](../romeo_mcp/documentation/README.md).

## Continuer

[Installer et démarrer](../README.md#prise-en-main) ·
[Contribuer](../CONTRIBUTING.md) ·
[Comprendre le code](../romeo_mcp/README.md)
