---
title: "Interface Web Oratio"
source: "https://romeo.univ-reims.fr/documentation/services/Oratio/gui_oratio"
scraped_at: "2026-09-26 02:37:11"
---

[Sommaire](../../SOMMAIRE.md) › [Accueil](../../index.md) › [Services](../../services.md) › [Oratio](../Oratio.md) › Interface Web Oratio · [Corpus ROMEO](../../README.md) · [Guides MCP](https://github.com/Gotman08/romeo-mcp/blob/main/docs/README.md) · [Tools](https://github.com/Gotman08/romeo-mcp/blob/main/docs/Tools.md)

# Interface Web Oratio

## Qu'est-ce qu'Oratio Web ?[​](#quest-ce-quoratio-web- "Lien direct vers Qu'est-ce qu'Oratio Web ?")

Oratio Web est l’interface **graphique (GUI)** qui permet aux utilisateurs de l’Université de Reims Champagne-Ardenne (URCA) d’interagir simplement avec des modèles d’intelligence artificielle générative (**LLM**).

Les modèles proposés sont hébergés sur des infrastructures académiques françaises, principalement sur **ROMEO** ou via le réseau national **ILaaS**.

Oratio Web repose sur le logiciel open source [OpenWebUI](https://github.com/open-webui/open-webui), customisé et intégré au contexte académique de l’URCA.

**But principal :** permettre aux étudiants, enseignants, chercheurs et personnels de l’URCA d'utiliser des modèles d'IA pour des tâches courantes telles que la rédaction, la synthèse, l'analyse de documents, la programmation ou l'aide à la compréhension, sans avoir à installer quoi que ce soit ni à écrire de code.

---

## Fonctionnalités principales[​](#fonctionnalités-principales "Lien direct vers Fonctionnalités principales")

- **Accès sécurisé par compte URCA** (SSO institutionnel)
- **Interface graphique simple** pour dialoguer avec les modèles
- **Accès à plusieurs modèles d'IA** hébergés sur ROMEO ou accessibles via ILaaS
- **Historique des conversations** dans OpenWebUI
- **Téléversement de documents** pour leur analyse ou leur interrogation, selon les capacités du modèle
- **Paramétrage avancé** : température, longueur maximale de réponse, *system prompt*, etc.
- **Mode RAG** permettant de questionner des documents
- **Streaming** : affichage progressif des réponses
- **Interrogation de plusieurs modèles simultanément** pour comparer leurs réponses

---

## À qui s'adresse Oratio Web ?[​](#à-qui-sadresse-oratio-web- "Lien direct vers À qui s'adresse Oratio Web ?")

Oratio s'adresse aux **étudiants, enseignants, chercheurs et personnels de l’URCA** qui souhaitent utiliser des modèles d'intelligence artificielle pour :

- rédiger ou reformuler des textes ;
- résumer des documents ;
- comprendre ou expliquer des concepts ;
- analyser des informations ;
- programmer ou corriger du code ;
- travailler avec des documents ;
- expérimenter avec différents modèles d'IA.

Aucun prérequis technique n'est nécessaire pour utiliser l'interface Web.

> **⚠️ REMARQUE :**
>
> L’accès est **réservé aux comptes URCA**.

---

## Fonctionnement général[​](#fonctionnement-général "Lien direct vers Fonctionnement général")

### 1. Connexion[​](#1-connexion "Lien direct vers 1. Connexion")

Rendez-vous sur [oratio.univ-reims.fr](https://oratio.univ-reims.fr/) et connectez-vous avec vos identifiants URCA.

### 2. Choix d'un modèle[​](#2-choix-dun-modèle "Lien direct vers 2. Choix d'un modèle")

Avant de commencer une conversation, vous pouvez choisir le modèle d'IA que vous souhaitez utiliser.

Les modèles disponibles sont proposés dans le sélecteur de modèles de l'interface. Leur disponibilité peut évoluer au fil des mises à jour de l'infrastructure.

### Comment choisir son modèle ?[​](#comment-choisir-son-modèle- "Lien direct vers Comment choisir son modèle ?")

Il n'est généralement **pas nécessaire de connaître les caractéristiques techniques des modèles** pour commencer.

Pour un usage courant, le **Modèle Généraliste** est recommandé. Cet alias est destiné à pointer vers un modèle récent et performant adapté aux tâches quotidiennes.

Pour des besoins particuliers, d'autres modèles sont disponibles.

#### Modèles ROMEO[​](#modèles-romeo "Lien direct vers Modèles ROMEO")

Les modèles dont le nom commence par `romeo.` sont hébergés sur l'infrastructure **ROMEO**.

On trouve notamment :

- **Modèle Généraliste** : modèle recommandé pour un usage général. Il pointe actuellement vers `romeo.mistral-small-3.2-24b`.
- **Modèle Intelligent** : modèle orienté vers le raisonnement, la programmation et les tâches dites « agentiques », c'est-à-dire nécessitant d'enchaîner plusieurs actions. Il est généralement moins rapide et moins adapté à la rédaction de textes. **Disponibilité à venir.**
- `romeo.mistral-small-3.2-24b` : modèle généraliste français, particulièrement adapté à la rédaction de textes en français. **Ancien modèle, bientôt retiré.**
- `romeo.mistral-small-4-119b` : nouveau modèle généraliste français. **Disponibilité à venir.**

#### Modèles ILaaS[​](#modèles-ilaas "Lien direct vers Modèles ILaaS")

Les modèles dont le nom commence par `ilaas.` sont accessibles via **ILaaS**, le réseau national académique de mise à disposition de modèles d'IA.

Ces modèles sont également hébergés en France.

On trouve notamment :

- `ilaas/mistral-small-4-119b` : modèle généraliste français, notamment adapté à la rédaction de textes en français.
- `ilaas/gemma-4-31b` : modèle généraliste.
- `ilaas/mistral-medium-latest` : modèle généraliste français de grande taille. Il offre davantage de capacités mais est généralement plus lent.
- `ilaas/qwen-3.6-35b-instruct` : modèle orienté vers le raisonnement.
- `ilaas/mistral-small-3.2-24b` : modèle généraliste français. **Ancien modèle, bientôt retiré.**
- `ilaas/gpt-oss-120b` : modèle orienté vers le raisonnement. **Ancien modèle, bientôt retiré.**

### Modèles « à la demande »[​](#modèles--à-la-demande- "Lien direct vers Modèles « à la demande »")

Les modèles dont le nom commence par `romeo.modelsondemand/` sont des modèles disponibles **à la demande**.

Ils ne sont chargés sur ROMEO que lorsqu'ils sont utilisés. **La première requête peut donc être sensiblement plus lente.**

Ces modèles peuvent être ajoutés ou retirés en fonction des besoins et des ressources disponibles.

---

### 3. Sélectionner un modèle[​](#3-sélectionner-un-modèle "Lien direct vers 3. Sélectionner un modèle")

1. Sous la zone de chat, cliquez sur le sélecteur de modèle.
2. Parcourez la liste des modèles disponibles.
3. Cliquez sur le modèle souhaité.
4. Vous pouvez également sélectionner plusieurs modèles simultanément avec le bouton `◊` afin de comparer leurs réponses.

---

### 4. Conversation[​](#4-conversation "Lien direct vers 4. Conversation")

Saisissez votre question ou votre consigne dans la fenêtre de chat.

Le modèle génère sa réponse progressivement. Vous pouvez poursuivre la conversation, demander des précisions ou modifier votre demande.

### Historique des conversations[​](#historique-des-conversations "Lien direct vers Historique des conversations")

Les conversations sont conservées dans **OpenWebUI** afin de permettre leur consultation ultérieure.

Vous pouvez supprimer vos conversations depuis l'interface.

**Une conversation supprimée dans OpenWebUI est supprimée du stockage d'Oratio et aucune copie n'en est conservée.**

---

### 5. Personnalisation avancée[​](#5-personnalisation-avancée "Lien direct vers 5. Personnalisation avancée")

Les paramètres accessibles depuis l'interface permettent notamment de modifier :

- **Température** : contrôle le degré de variabilité des réponses ;
- **Longueur maximale de la réponse** ;
- **System prompt** : consignes générales permettant de modifier le comportement du modèle.

Ces paramètres sont principalement destinés aux utilisateurs souhaitant contrôler plus finement le comportement du modèle.

---

### 6. Téléversement de documents[​](#6-téléversement-de-documents "Lien direct vers 6. Téléversement de documents")

Vous pouvez joindre des documents afin de demander au modèle de les analyser, les résumer ou répondre à des questions à leur sujet.

Les capacités disponibles dépendent du modèle utilisé et des limites techniques en vigueur.

> **⚠️ À noter :**
>
> Les capacités de stockage et d'analyse documentaire sont actuellement limitées. Les fichiers joints pourront être supprimés en cas de surcharge de l'espace de stockage.
> Une solution plus avancée de gestion documentaire par intelligence artificielle est en cours de conception par ROMEO.

---

## Exemples d'utilisation[​](#exemples-dutilisation "Lien direct vers Exemples d'utilisation")

- **Modèle Généraliste** : rédaction d'un courriel, reformulation, résumé, explication d'un concept, brainstorming, etc.
- **Modèle Intelligent** : raisonnement complexe, programmation, analyse nécessitant plusieurs étapes, lorsque ce modèle sera disponible.
- **Mistral Small** : rédaction et traitement de textes en français.
- **Mistral Medium** : tâches générales nécessitant davantage de capacités, au prix d'une vitesse généralement plus faible.
- **Modèles à la demande** : expérimentation avec des modèles spécifiques qui ne sont pas maintenus en permanence en mémoire.

N'hésitez pas à expérimenter : selon la tâche, un modèle peut produire des résultats sensiblement différents d'un autre.

---

## Liens avec l'API Oratio et ILaaS[​](#liens-avec-lapi-oratio-et-ilaas "Lien direct vers Liens avec l'API Oratio et ILaaS")

- **Oratio Web** permet d'utiliser graphiquement les modèles disponibles dans l'infrastructure Oratio.
- **L'API Oratio** permet d'accéder aux modèles de manière automatisée, notamment depuis des programmes Python ou d'autres applications.
- **ILaaS** fournit également des modèles accessibles depuis Oratio.

Pour les utilisations programmatiques, consultez la [documentation de l'API Oratio](../../services/Oratio/api_oratio.md).

---

## Limitations et bonnes pratiques[​](#limitations-et-bonnes-pratiques "Lien direct vers Limitations et bonnes pratiques")

### Capacité de calcul[​](#capacité-de-calcul "Lien direct vers Capacité de calcul")

Les ressources de calcul étant partagées, une forte demande peut entraîner un ralentissement de certains modèles.

En cas de ralentissement, vous pouvez essayer un modèle moins volumineux ou un autre modèle disponible.

### Stockage[​](#stockage "Lien direct vers Stockage")

OpenWebUI conserve les conversations que vous choisissez de conserver dans votre historique.

Les fichiers téléversés sont également soumis aux limites de stockage du service. Ils pourront être supprimés en cas de surcharge de l'espace disponible.

### Confidentialité[​](#confidentialité "Lien direct vers Confidentialité")

Les modèles et services d'inférence ne conservent pas le contenu des échanges une fois leur traitement terminé.

**OpenWebUI conserve en revanche les conversations afin de fournir la fonctionnalité d'historique.** Si vous supprimez une conversation depuis OpenWebUI, elle est supprimée du stockage d'Oratio et aucune copie n'en est conservée.

Les échanges ne sont pas utilisés pour entraîner ou améliorer les modèles proposés dans Oratio.

### Bon usage[​](#bon-usage "Lien direct vers Bon usage")

Comme avec tout système d'intelligence artificielle, les réponses générées doivent être vérifiées, notamment lorsqu'elles sont utilisées dans un contexte scientifique, administratif ou professionnel.

Un modèle peut produire des informations incorrectes ou présenter avec assurance une réponse erronée. Ne considérez donc pas ses réponses comme automatiquement fiables.

---

## Documentation complémentaire[​](#documentation-complémentaire "Lien direct vers Documentation complémentaire")

- [Documentation de l'API Oratio](../../services/Oratio/api_oratio.md)
- [Documentation ROMEO](https://romeo.univ-reims.fr/documentation/services/Oratio/gui_oratio)
- [Documentation API Oratio sur ROMEO](https://romeo.univ-reims.fr/documentation/services/Oratio/api_oratio)

---

← [Oratio](../Oratio.md) | → [API Oratio](api_oratio.md)

## Dans cette section

[↑ Haut de page](#interface-web-oratio) · [Sommaire officiel](../../SOMMAIRE.md) · [Guide du corpus](../../README.md)
