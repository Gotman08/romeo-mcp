---
title: "RomeoLLMTool - Présentation"
source: "https://romeo.univ-reims.fr/documentation/services/RomeoLLMtool"
scraped_at: "2026-10-16 15:47:05"
---

[Sommaire](../SOMMAIRE.md) › [Accueil](../index.md) › [Services](../services.md) › RomeoLLMTool · [Corpus ROMEO](../README.md) · [Guides MCP](https://github.com/Gotman08/romeo-mcp/blob/main/docs/README.md) · [Tools](https://github.com/Gotman08/romeo-mcp/blob/main/docs/Tools.md)

# RomeoLLMTool - Présentation

romeollmtool lance et pilote des modèles de langage (LLM) sur le cluster ROMEO,
via Slurm, avec vLLM, SGLang ou llama.cpp (llama-server).

## État du projet[​](#état-du-projet "Lien direct vers État du projet")

> ⚠️ **Attention**
>
> info

romeollmtool est encore en **préproduction**. Les sources seront prochainement
ouvertes sur RomeoGIT.

## Accès[​](#accès "Lien direct vers Accès")

L'outil n'est accessible que depuis le réseau de l'URCA, ou via son VPN.
Depuis l'extérieur, le plus simple est un pont SSH entre votre machine et le
nœud de connexion utilisé :

> ⚠️ **Attention**
>
> Accéder depuis l'extérieur du réseau URCA
```bash
ssh -L 11361:localhost:11361 <identifiant>@romeo1.univ-reims.fr
```

Remplacez le port par celui donné par `romeollmtool gateway start` (ou
`gateway status`), et `romeo1` par le nœud de connexion effectivement
utilisé. Le pont ouvert, utilisez `http://localhost:11361/v1` depuis votre
machine, avec la même clé API (`romeollmtool gateway show-key`).

En cas de problème, ouvrez un ticket sur le système de support de ROMEO.

![Aperçu de l&#39;interface terminal : onglet Catalogue, liste des fiches et détail](../images/1-4c738669c41b77ade86e78463574ffcc_b495b68a.png)

## Ce que l'outil fait[​](#ce-que-loutil-fait "Lien direct vers Ce que l'outil fait")

- un catalogue de modèles vérifiés, partagé entre tous les utilisateurs
- des fiches personnelles pour lancer vos propres modèles et réglages
- le lancement et la surveillance d'un modèle en une commande, ou depuis
  l'interface terminal
- une gateway persistante compatible avec l'API OpenAI : une URL et une clé
  pour tous vos modèles lancés
- un chat intégré pour tester un modèle sans écrire de code
- une vérification automatique d'une fiche (`verify`) avant de s'en servir au
  quotidien

## Deux façons de l'utiliser[​](#deux-façons-de-lutiliser "Lien direct vers Deux façons de l'utiliser")

- `romeollmtool`, sans argument, ouvre l'**interface terminal** : voir
  [Interface terminal](../services/RomeoLLMtool/gui.md).
- chaque action de l'interface existe aussi en **sous-commande** : voir
  [Ligne de commande](../services/RomeoLLMtool/cli.md).

Les deux appellent le même code : rien ne diffère entre elles, sauf la
présentation. Choisissez selon votre confort : aucune des deux n'est plus
complète que l'autre, hormis l'administration du catalogue partagé, réservée
à une commande à part (`romeollmtool-admin`), destinée aux administrateurs du
cluster.

## Vocabulaire[​](#vocabulaire "Lien direct vers Vocabulaire")

| Terme | Sens |
| --- | --- |
| **fiche** | fichier YAML qui décrit un modèle et comment le servir. Voir [Écrire une fiche](../services/RomeoLLMtool/fiches.md). |
| **catalogue** | fiches partagées entre tous les utilisateurs, proposées par merge request, vérifiées puis validées par un administrateur. |
| **fiche perso** | votre propre fiche, dans `~/.romeollmtool/configs/`. Peut compléter une fiche du catalogue ou être autonome. |
| **moteur** | le serveur d'inférence qui fait réellement tourner le modèle : vLLM, SGLang ou llama.cpp. Voir [Moteurs](../services/RomeoLLMtool/engines.md). |
| **job** | l'exécution Slurm d'un modèle lancé à partir d'une fiche. |
| **gateway** | proxy persistant, compatible OpenAI, qui donne accès à tous vos modèles lancés par une seule URL et une seule clé. Voir [Utiliser l'API](../services/RomeoLLMtool/api.md). |
| **vérifier** | lancer un vrai job, le tester (réponse, streaming, vision selon le cas), l'arrêter, et écrire un rapport (`romeollmtool verify`). |

## Pour aller plus loin[​](#pour-aller-plus-loin "Lien direct vers Pour aller plus loin")

- [Interface terminal](../services/RomeoLLMtool/gui.md) : l'interface qui s'ouvre sans argument
- [Ligne de commande](../services/RomeoLLMtool/cli.md) : toutes les sous-commandes
- [Écrire une fiche](../services/RomeoLLMtool/fiches.md) : format, fiche perso, licences, catégories
- [Moteurs](../services/RomeoLLMtool/engines.md) : vLLM, SGLang, llama.cpp, variantes, moteur perso
- [Utiliser l'API](../services/RomeoLLMtool/api.md) : intégrer un modèle servi dans un autre outil

## Dans cette section

- [Interface terminal](RomeoLLMtool/gui.md)
- [Ligne de commande](RomeoLLMtool/cli.md)
- [Écrire une fiche](RomeoLLMtool/fiches.md)
- [Moteurs](RomeoLLMtool/engines.md)
- [Utiliser l'API](RomeoLLMtool/api.md)

---

← [Assistance](assistance.md) | → [Interface terminal](RomeoLLMtool/gui.md)

[↑ Haut de page](#romeollmtool---présentation) · [Sommaire officiel](../SOMMAIRE.md) · [Guide du corpus](../README.md)
