# Outil RomeoLLMTool

[Corpus ROMEO](../../README.md) › [Services](../README.md) › RomeoLLMTool

Cette section conserve les pages officielles de RomeoLLMTool, l’outil qui lance
et pilote des modèles de langage (LLM) sur le cluster par Slurm. La
[présentation de l’outil](../RomeoLLMtool.md) décrit son état de préproduction,
ses conditions d’accès et son vocabulaire avant toute utilisation.

**Sur cette page :** [Parcours de lecture](#parcours-de-lecture) · [Lien avec le MCP](#lien-avec-le-mcp)

## Parcours de lecture

| Usage | Page officielle |
|---|---|
| Découvrir l’outil, l’accès et le vocabulaire | [Présentation](../RomeoLLMtool.md) |
| Lancer et suivre un modèle au clavier | [Interface terminal](gui.md) |
| Automatiser avec les sous-commandes | [Ligne de commande](cli.md) |
| Décrire un modèle et sa façon de le servir | [Écrire une fiche](fiches.md) |
| Choisir entre vLLM, SGLang et llama.cpp | [Moteurs](engines.md) |
| Appeler les modèles lancés depuis un programme | [Utiliser l’API](api.md) |

Pour utiliser un modèle déjà hébergé sans lancer de job, le
[service Oratio](../Oratio/README.md) propose une interface web et une API.
Les commandes, ports et modèles cités sont ceux de la collecte embarquée ;
le lien `source` de chaque page permet de consulter la version officielle.

## Lien avec le MCP

Le MCP permet de retrouver ces procédures avec [`search_docs`](https://github.com/Gotman08/romeo-mcp/blob/main/docs/tools/search_docs.md) et [`read_doc`](https://github.com/Gotman08/romeo-mcp/blob/main/docs/tools/read_doc.md).
RomeoLLMTool s’utilise avec sa propre commande depuis ROMEO, selon sa
documentation et ses conditions d’accès. Pour les calculs soumis par Slurm,
suivre le [parcours ROMEO 2025](../../ressources/romeo_2025/README.md).

[Retour aux services](../README.md) · [Sommaire officiel](../../SOMMAIRE.md)

*Guide de navigation du projet MCP ; les pages liées proviennent de ROMEO / URCA.*

---

[↑ Haut de page](#outil-romeollmtool) · [Corpus ROMEO](../../README.md) · [Sommaire officiel](../../SOMMAIRE.md) · [Guides MCP](https://github.com/Gotman08/romeo-mcp/blob/main/docs/README.md) · [Tools](https://github.com/Gotman08/romeo-mcp/blob/main/docs/Tools.md)
