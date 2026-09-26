# Documentation du MCP ROMEO

[Accueil du projet](../README.md) › Documentation

Ce dossier explique comment utiliser le MCP et comprendre ses résultats.
Les procédures du centre de calcul sont conservées dans le
[corpus officiel ROMEO](../romeo_mcp/documentation/README.md), avec leurs sources
et leur date de collecte.

## Choisir un parcours

| Vous souhaitez… | Point de départ | Étape suivante |
|---|---|---|
| Installer le MCP pour un cours ou un projet | [Prise en main](../README.md#prise-en-main) | [Configuration et diagnostic](configuration.md) |
| Lancer votre premier calcul | [Premier essai](../README.md#4-faire-un-premier-essai) | [Outils et calcul parallèle](reference.md) |
| Présenter moins d’outils à l’IA | [Profils d’outils](configuration.md#profils-doutils) | [Catalogue complet](reference.md#outils-exposés) |
| Comprendre un refus ou un échec | [Diagnostic des accès](configuration.md#diagnostic-en-lecture-seule) | [Diagnostic des jobs](reference.md#diagnostic-des-échecs) |
| Conserver les conditions d’une expérience | [Fiches de reproductibilité](reproducibility.md) | [Mesures et limites](reproducibility.md#ce-qui-est-réellement-mesuré) |
| Vérifier une procédure ROMEO | [Sommaire officiel embarqué](../romeo_mcp/documentation/SOMMAIRE.md) | [Recherche et lecture par sections](reference.md#recherche-et-contexte-pour-le-modèle) |
| Contribuer au projet | [Architecture du code](../romeo_mcp/README.md) | [Tests](../tests/README.md) et [contribution](../CONTRIBUTING.md) |

## Les guides

- [Configuration](configuration.md) : accès personnels, priorités des réglages,
  profils `essential` et `full`, clients stdio, `doctor --live`, déplacement et WSL.
- [Référence technique](reference.md) : outils MCP, MPI et GPU, logiciels,
  stockage, diagnostics, mesures et limites de conception.
- [Reproductibilité](reproducibility.md) : capture des informations d’un job,
  empreintes des entrées, export privé, dates d’observation et données manquantes.
- [Visuels](assets/README.md) : schéma de fonctionnement, bannière et attributions.

## Lire un résultat dans son contexte

La simulation d’un job produit un script et des avertissements. La soumission
donne un identifiant Slurm. L’état `COMPLETED` indique la fin du processus ;
la validité scientifique reste à vérifier dans les résultats de l’expérience.

Pour interpréter une fiche ou un diagnostic, conserver ensemble la source,
la date, les paramètres et les limites indiquées. Le corpus embarqué est une
copie datée ; les accès et quotas effectifs se vérifient avec les outils distants.
Les extraits de recherche conduisent aux sections complètes via `read_doc`.

## Repères pour les contributeurs

| Section | Ce qu’elle documente |
|---|---|
| [Code Python](../romeo_mcp/README.md) | Responsabilités des modules et trajet d’un appel |
| [Utilitaires](../tools/README.md) | Installation des clients, contrôle de confidentialité et entretien du corpus |
| [Tests](../tests/README.md) | Suites hors ligne et essais sur ROMEO |
| [GitHub](../.github/README.md) | Vérifications automatiques du dépôt |
| [Hooks Git](../.githooks/README.md) | Contrôles locaux avant commit et push |

Pour signaler une vulnérabilité, suivre [SECURITY.md](../SECURITY.md).
Pour les règles de redistribution, consulter la [licence](../LICENSE) et
les [mentions des contenus tiers](../THIRD_PARTY_NOTICES.md).
