---
title: "API Oratio"
source: "https://romeo.univ-reims.fr/documentation/services/Oratio/api_oratio"
scraped_at: "2026-09-26 02:37:10"
---

[Sommaire](../../SOMMAIRE.md) › [Accueil](../../index.md) › [Services](../../services.md) › [Oratio](../Oratio.md) › API Oratio

# API Oratio

## Introduction[​](#introduction "Lien direct vers Introduction")

Cette documentation présente l’API LLM accessible via ROMEO, utilisée à l’URCA pour accéder :

- soit aux **modèles hébergés localement** sur le **serveur Oratio LLM** (ROMEO),
- soit aux **modèles distribués** du réseau national **ILaaS – Inference LLM as a Service**.

> **⚠️ Accès API** : L’utilisation de l’API LiteLLM n’est possible **qu’après soumission et évaluation d’un projet**, conformément aux règles d’accès ILaaS et aux politiques internes URCA. Vous pourrez n'avoir accès qu'a certains modèles, et avoir un quota d'utilisation.

---

## Configuration de base[​](#configuration-de-base "Lien direct vers Configuration de base")

**URL de l'API** : `https://romeogate.univ-reims.fr/llm`
**Clé d'API (exemple)** : `sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` - clé obtenue auprès de ROMEO dans le cadre d'un projet
**Format API** : OpenAI Compatible

La clé d'API doit rester secrète et **vous en êtes responsable**, toute personne en possession de cette clé pourra utiliser l'API **en votre nom**, et sur vos quotas. Si besoin, vous pouvez contacter ROMEO ([romeo@univ-reims.fr](mailto:romeo@univ-reims.fr)) pour vérifier les statistiques d'utilisation de cette clé, et si besoin l'invalider et en générer une nouvelle.

---

## Endpoints de l'API[​](#endpoints-de-lapi "Lien direct vers Endpoints de l'API")

(Un endpoint est une URL de l'API pouvant être interrogée et dédiée à une fonctionnalité)

Cette API fonctionne coté ROMEO via l'outil LiteLLM et implémente les endpoints principaux de la norme API OpenAI, nous allons explorer les endpoint suivants dans cette documentation :

| Endpoint | Méthode | Description |
| --- | --- | --- |
| `/models` | GET | Liste les modèles disponibles |
| `/chat/completions` | POST | Génération de chat/completion (streaming supporté) |

---

## Paramètres de génération[​](#paramètres-de-génération "Lien direct vers Paramètres de génération")

Voici une liste des paramètres que nous allons utiliser petit à petit tout au long de ce document

### Paramètres principaux[​](#paramètres-principaux "Lien direct vers Paramètres principaux")

| Paramètre | Type | Range | Description |
| --- | --- | --- | --- |
| **max\_tokens** | integer | 1-4096+ | Nombre maximum de tokens à générer dans la réponse. Plus ce nombre est élevé, plus la réponse peut être longue. La valeur maximale supportée dépend du modèle utilisé |
| **temperature** | float | 0.0-2.0 | Contrôle la créativité/aléatoire. 0.0 = déterministe et cohérent, 1.0 = équilibré, 2.0 = très créatif et imprévisible |
| **top\_p** | float | 0.0-1.0 | Nucleus sampling. 0.1 = seuls les tokens les plus probables, 0.9 = plus de diversité dans les choix |
| **frequency\_penalty** | float | -2.0-2.0 | Pénalise la répétition de tokens selon leur fréquence. Valeurs positives réduisent les répétitions |
| **presence\_penalty** | float | -2.0-2.0 | Pénalise la répétition de tokens déjà présents. Encourage l'exploration de nouveaux sujets |
| **reasoning\_effort** | string | low/medium/high | Si le modèle est capable de raisonnement, ce paramètre permet de définir le niveau de réflexion pratiqué par le modèle avant de former sa réponse à l'utilisateur |

### Recommandations d'usage[​](#recommandations-dusage "Lien direct vers Recommandations d'usage")

Vous pouvez ne pas préciser ces valeurs qui sont parfaitement optionnelles, mais si vous souhaitez tenter d'affiner la réponse du modèle, nous conseillons par exemple pour les cas suivants :

| Cas d'usage | temperature | top\_p | max\_tokens | Exemple |
| --- | --- | --- | --- | --- |
| **Code/Technique** | 0.1-0.3 | 0.9 | 500-1000 | Génération de code, documentation technique |
| **Rédaction** | 0.7-0.9 | 0.9 | 800-1500 | Articles, emails, rapports |
| **Créatif** | 0.8-1.2 | 0.9-0.95 | 1000+ | Histoires, poèmes, brainstorming |
| **Analyse** | 0.3-0.5 | 0.9 | 600-1200 | Résumés, analyses de données |

---

## 1. Appels directs avec curl[​](#1-appels-directs-avec-curl "Lien direct vers 1. Appels directs avec curl")

Avant d'utiliser un framework, nous allons faire quelques exemples 'brutes' de requêtes envoyés via la comment curl.

**Dans tous les exemples de ce document, pensez toujours à remplacer la clé d'exemple (invalide) "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" par la votre.**

### 1.1 Liste des modèles disponibles[​](#11-liste-des-modèles-disponibles "Lien direct vers 1.1 Liste des modèles disponibles")

```bash
curl -X GET "https://romeogate.univ-reims.fr/llm/models" \
  -H "Authorization: Bearer sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" \
  -H "Content-Type: application/json"
```

**Résultat (formaté):**

```json
{
    "data": [
        {
            "id": "ilaas/*",
            "object": "model",
            "created": 1677610602,
            "owned_by": "openai"
        },
        {
            "id": "gpt-oss-120b",
            "object": "model",
            "created": 1677610602,
            "owned_by": "openai"
        },
        {
            "id": "Qwen3-Embedding-0.6B",
            "object": "model",
            "created": 1677610602,
            "owned_by": "openai"
        },
        {
            "id": "mistral-small-3.2-24b",
            "object": "model",
            "created": 1677610602,
            "owned_by": "openai"
        },
        {
            "id": "ilaas/gpt-oss-120b",
            "object": "model",
            "created": 1677610602,
            "owned_by": "openai"
        },
        {
            "id": "ilaas/llama-3.1-8b",
            "object": "model",
            "created": 1677610602,
            "owned_by": "openai"
        },
        {
            "id": "ilaas/llama-3.3-70b",
            "object": "model",
            "created": 1677610602,
            "owned_by": "openai"
        },
        {
            "id": "ilaas/mistral-small-3.2-24b",
            "object": "model",
            "created": 1677610602,
            "owned_by": "openai"
        },
        {
            "id": "ilaas/qwen-2.5-3b",
            "object": "model",
            "created": 1677610602,
            "owned_by": "openai"
        },
        {
            "id": "ilaas/qwen-3-30b",
            "object": "model",
            "created": 1677610602,
            "owned_by": "openai"
        }
    ],
    "object": "list"
}
```

Le modèle `ilaas/*` est un pseudo modèle interne utilisé par LiteLLM, n'utilisez pas ce modèle, il ne fonctionnera pas si requêté.

Certaines modèles ne sont pas des LLM mais des modèles spécialisés, referez vous à leur nom. Par exemple `Qwen3-Embedding-0.6B` est un modèle d'embedding et non un LLM.
Ces modèles serons séparés des modèles LLM et utilisables via une clé dédiée prochainement.

Les modèles préfixés par «ilaas/» sont ceux fournis par le service IlaaS.
Les modèles ROMEO faisant partie des modèles mis à disposition via IlaaS, vous les trouverez en double:

- sans le préfix ilaas/ pour une utilisation directe via ROMEO
- et avec le préfixe ilaas/ pour les utiliser via IlaaS.

En fonction des autorisations de votre clé, vous pouvez avoir accès uniquement aux modèles IlaaS, ou uniquement aux modèles ROMEO.

### 1.2 Génération de texte simple[​](#12-génération-de-texte-simple "Lien direct vers 1.2 Génération de texte simple")

```bash
curl -X POST "https://romeogate.univ-reims.fr/llm/chat/completions" \
  -H "Authorization: Bearer sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mistral-small-3.2-24b",
    "messages": [
      {
        "role": "user",
        "content": "Bonjour, peux-tu te présenter ?"
      }
    ],
    "max_tokens": 150,
    "temperature": 0.7
  }'
```

**Résultat (formaté):**

```json
{
  "id": "chatcmpl-17f15df588ca429b8ff195a671434c6a",
  "created": 1758101853,
  "model": "mistral-small-3.2-24b",
  "object": "chat.completion",
  "choices": [
    {
      "finish_reason": "stop",
      "index": 0,
      "message": {
        "content": "Bonjour ! Je suis une intelligence artificielle conçue pour t'aider dans diverses tâches : répondre à tes questions, te fournir des informations, t'aider à rédiger des textes, résoudre des problèmes, et bien plus encore.\n\nJe peux discuter de sujets variés (science, culture, technologie, etc.), t'assister dans tes projets ou simplement échanger des idées. Mon but est de te rendre la vie plus facile et plus agréable.\n\nComment puis-je t'aider aujourd'hui ? 😊",
        "role": "assistant"
      },
      "provider_specific_fields": {
        "stop_reason": null
      }
    }
  ],
  "usage": {
    "completion_tokens": 105,
    "prompt_tokens": 11,
    "total_tokens": 116
  }
}
```

### 1.3 Génération en streaming[​](#13-génération-en-streaming "Lien direct vers 1.3 Génération en streaming")

Le mode Streaming permet d'avoir le résultat de la génération au fur et à mesure qu'il est généré par le modèle LLM

```bash
curl -X POST "https://romeogate.univ-reims.fr/llm/chat/completions" \
  -H "Authorization: Bearer sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mistral-small-3.2-24b",
    "messages": [
      {
        "role": "user",
        "content": "Raconte-moi une histoire courte"
      }
    ],
    "max_tokens": 200,
    "temperature": 0.8,
    "stream": true
  }' \
  --no-buffer
```

Nous allons recevoir en temps réel chaque bout de la réponse au fut et à mesure qu'il est généré :

**Résultat (flux SSE) :**

```json
data: {"id":"chatcmpl-e5a05a7e316343f7b8872bf56c5b2e6e","created":1758101968,"model":"mistral-small-3.2-24b","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"**","role":"assistant"}}]}

data: {"id":"chatcmpl-e5a05a7e316343f7b8872bf56c5b2e6e","created":1758101968,"model":"mistral-small-3.2-24b","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"Le"}}]}

data: {"id":"chatcmpl-e5a05a7e316343f7b8872bf56c5b2e6e","created":1758101968,"model":"mistral-small-3.2-24b","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":" Gard"}}]}

data: {"id":"chatcmpl-e5a05a7e316343f7b8872bf56c5b2e6e","created":1758101968,"model":"mistral-small-3.2-24b","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"ien"}}]}

data: {"id":"chatcmpl-e5a05a7e316343f7b8872bf56c5b2e6e","created":1758101968,"model":"mistral-small-3.2-24b","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":" du"}}]}

data: {"id":"chatcmpl-e5a05a7e316343f7b8872bf56c5b2e6e","created":1758101968,"model":"mistral-small-3.2-24b","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":" Ph"}}]}

data: {"id":"chatcmpl-e5a05a7e316343f7b8872bf56c5b2e6e","created":1758101968,"model":"mistral-small-3.2-24b","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"are"}}]}

data: {"id":"chatcmpl-e5a05a7e316343f7b8872bf56c5b2e6e","created":1758101968,"model":"mistral-small-3.2-24b","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"**\n\n"}}]}

data: {"id":"chatcmpl-e5a05a7e316343f7b8872bf56c5b2e6e","created":1758101968,"model":"mistral-small-3.2-24b","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"Sur"}}]}

data: {"id":"chatcmpl-e5a05a7e316343f7b8872bf56c5b2e6e","created":1758101968,"model":"mistral-small-3.2-24b","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":" une"}}]}

data: {"id":"chatcmpl-e5a05a7e316343f7b8872bf56c5b2e6e","created":1758101968,"model":"mistral-small-3.2-24b","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":" île"}}]}

data: {"id":"chatcmpl-e5a05a7e316343f7b8872bf56c5b2e6e","created":1758101968,"model":"mistral-small-3.2-24b","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":" isol"}}]}

//[...]  La réponse était longue, nous l'avons tronquée ici
```

---

## 2. Utilisation avec le package Python OpenAI[​](#2-utilisation-avec-le-package-python-openai "Lien direct vers 2. Utilisation avec le package Python OpenAI")

Afin de simplifier nos interactions avec l'API, nous pouvons utiliser un Framework.
Nous allons utiliser ici Python3 et son framework OpenAI.

De nombreux autres framework existent pour d'autres langages de programmation. Referez vous à leur documentation respective.

### 2.1 Installation[​](#21-installation "Lien direct vers 2.1 Installation")

```bash
pip install "openai>=1"
```

### 2.2 Configuration du client[​](#22-configuration-du-client "Lien direct vers 2.2 Configuration du client")

Au début de votre script, ajoutez toujours la déclaration de votre client :

```python
from openai import OpenAI

# Configuration du client pour notre API
client = OpenAI(
    api_key="sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    base_url="https://romeogate.univ-reims.fr/llm"
)
```

### 2.3 Liste des modèles disponibles[​](#23-liste-des-modèles-disponibles "Lien direct vers 2.3 Liste des modèles disponibles")

```python
# Récupération de la liste des modèles
try:
    models = client.models.list()
    print("Modèles disponibles :")
    for model in models.data:
        print(f"- {model.id}")
except Exception as e:
    print(f"Erreur lors de la récupération des modèles : {e}")
```

**Résultat :**

```text
Modèles disponibles :
- ilaas/*
- gpt-oss-120b
- Qwen3-Embedding-0.6B
- mistral-small-3.2-24b
- ilaas/gpt-oss-120b
- ilaas/llama-3.1-8b
- ilaas/llama-3.3-70b
- ilaas/mistral-small-3.2-24b
- ilaas/qwen-2.5-3b
- ilaas/qwen-3-30b
```

### 2.4 Génération de réponse simple[​](#24-génération-de-réponse-simple "Lien direct vers 2.4 Génération de réponse simple")

```python
# Génération d'une réponse simple
try:
    response = client.chat.completions.create(
        model="mistral-small-3.2-24b",  # Remplacez par un modèle disponible
        messages=[
            {
                "role": "system",
                "content": "Tu es un assistant IA serviable et bienveillant."
            },
            {
                "role": "user",
                "content": "Explique-moi en quelques phrases ce qu'est l'intelligence artificielle."
            }
        ],
        max_tokens=200,
        temperature=0.7
    )

    print("Réponse du modèle :")
    print(response.choices[0].message.content)
    print(f"\nUtilisation de tokens : {response.usage.total_tokens}")

except Exception as e:
    print(f"Erreur lors de la génération : {e}")
```

**Résultat :**

```text
Réponse du modèle :
L'intelligence artificielle (IA) est un domaine de l'informatique qui vise à créer des systèmes capables d'effectuer des tâches qui nécessitent normalement l'intelligence humaine. Cela inclut la reconnaissance de la parole, la prise de décision, la traduction de langues, la résolution de problèmes et bien plus encore. L'IA repose sur des algorithmes et des modèles qui apprennent à partir de données, un processus appelé apprentissage automatique (machine learning). L'objectif est de développer des machines qui peuvent s'adapter, apprendre et améliorer leurs performances au fil du temps.

Utilisation de tokens : 152
```

### 2.5 Génération avec streaming[​](#25-génération-avec-streaming "Lien direct vers 2.5 Génération avec streaming")

```python
# Génération avec streaming
try:
    stream = client.chat.completions.create(
        model="mistral-small-3.2-24b",
        messages=[
            {
                "role": "user",
                "content": "Écris une nouvelle sur l'automne en 500 mots."
            }
        ],
        max_tokens=3000,
        temperature=0.8,
        stream=True
    )

    print("Réponse en streaming :")
    for chunk in stream:
        if chunk.choices[0].delta.content is not None:
            print(chunk.choices[0].delta.content, end="", flush=True)
    print()

except Exception as e:
    print(f"Erreur lors du streaming : {e}")
```

**Résultat :**

```text
Réponse en streaming :
**Les Feux de l'Automne**

L’automne s’installait doucement dans la petite ville d’Émeraude. Les feuilles des érables, d’abord dorées, viraient au rouge flamboyant, tandis que les chênes conservaient une teinte cuivrée. Clara, une vieille femme aux cheveux argentés, observait depuis sa fenêtre ce spectacle annuel, un sourire mélancolique aux lèvres.

Elle aimait cette saison, mais cette année, quelque chose lui semblait différent. Peut-être était-ce le silence plus lourd, le vent qui murmurait des secrets oubliés, ou bien les ombres plus longues qui s’étiraient sur le sol. Elle décida de sortir, malgré le froid mordant, pour marcher jusqu’au vieux cimetière où reposait son mari.

Les pavés étaient glissants, parsemés de feuilles mortes qui craquaient sous ses pas. En passant devant la bibliothèque municipale, elle remarqua une lumière allumée. À travers la vitre, elle aperçut un homme jeune, penché sur un livre. Il leva les yeux et leurs regards se croisèrent un instant. Elle ne savait pas pourquoi, mais elle sentit qu’il attendait quelque chose.

Le cimetière était paisible, enveloppé d’une brume légère. Clara s’agenouilla devant la tombe de Julien, effleurant les lettres usées par le temps. « L’hiver approche, murmura-t-elle. Tu te souviens de nos balades en forêt quand les châtaignes tombaient ? »

Soudain, un bruissement la fit sursauter. Derrière elle, l’homme de la bibliothèque se tenait, un bouquet de chrysanthèmes à la main. « Je… je cherche la tombe de ma mère, avoua-t-il. Elle est morte l’automne dernier. »

Clara hocha la tête, comprenant sa peine. « Moi aussi, je viens ici souvent. L’automne est une saison de souvenirs. »

Ils marchèrent ensemble entre les stèles, échangeant des histoires de ceux qu’ils avaient aimés. Le jeune homme, Thomas, raconta comment sa mère adorait les pommes et faisait chaque année une tarte pour son anniversaire. Clara évoqua Julien, qui sculptait des figurines en bois et les offrait aux enfants du quartier.

Quand le soleil commença à descendre, ils prirent le chemin du retour. « Merci, dit Thomas. Je ne savais pas que le chagrin pouvait devenir plus léger en le partageant. »

Clara sourit. « L’automne nous rappelle que la vie continue. Les feuilles tombent, mais au printemps, de nouvelles bourgeonnent. »

En rentrant chez elle, elle sentit une douceur inattendue dans l’air. Peut-être était-ce le vent d’automne, porteur de promesses, ou simplement le poids de sa solitude qui s’allégeait un peu. Elle alluma la radio et écouta une mélodie ancienne, celle que Julien jouait autrefois à l’harmonica.

Dehors, les derniers rayons du soleil embrasaient les toits, teintant la ville de rouge et d’or. L’automne, cette saison des adieux et des renaissances, avait encore une fois accompli sa magie.
```

La particularité du mode streaming, est que vous verrez cette réponse apparaitre petit à petit au fur et a mesure de la génération, et non en une fois une fois le texte complet généré par l'API.

Ce sera dynamique car géré par le framework et non affiché en brut comme dans l'exemple avec curl.

### 2.6 Génération avec raisonnement bas, moyen ou haut.[​](#26-génération-avec-raisonnement-bas-moyen-ou-haut "Lien direct vers 2.6 Génération avec raisonnement bas, moyen ou haut.")

Certains modèles (comme les modèles de type "reasoning") peuvent être optimisés pour des tâches de raisonnement complexe, ici nous allons utiliser gpt-oss-120b qui possède cette capacité :

```python
#Sans paramètre de raisonnement précisé
response = client.chat.completions.create(
    model="gpt-oss-120b",
    messages=[{"role": "user", "content": "Quel est le résultat de (2+2)*2/3 ? Explique les étapes du calcul"}],
)
print("Result:", response)

#Raisonnement Bas
response = client.chat.completions.create(
    model="gpt-oss-120b",
    messages=[{"role": "user", "content": "Quel est le résultat de (2+2)*2/3 ? Explique les étapes du calcul"}],
    reasoning_effort="low",
)
#print("Result low:", response)
print("Result:", response)

#Raisonnement Moyen
response = client.chat.completions.create(
    model="gpt-oss-120b",
    messages=[{"role": "user", "content": "Quel est le résultat de (2+2)*2/3 ? Explique les étapes du calcul"}],
    reasoning_effort="medium",
)
#print("Result medium:", response)
print("Result:", response)

#Raisonnement Haut
response = client.chat.completions.create(
    model="gpt-oss-120b",
    messages=[{"role": "user", "content": "Quel est le résultat de (2+2)*2/3 ? Explique les étapes du calcul"}],
    reasoning_effort="high",
)
print("Result:", response)
```

J'obtiens les réponses suivantes, on peut voir que dans le champs 'reasoning\_content' nous pouvons obtenir le contenu de sa réflexion:

```python
#Sans paramètre de raisonnement précisé
Result: ChatCompletion(
    id="chatcmpl-c5e1a59e5edb4c7c8989cc0f6c3e384d",
    choices=[
        Choice(
            finish_reason="stop",
            index=0,
            logprobs=None,
            message=ChatCompletionMessage(
                content="**Calcul étape par étape**\n\n1. **Parenthèses**  \n   \\[\n   (2+2)=4\n   \\]\n\n2. **Multiplication**  \n   Le résultat de la parenthèse est multiplié par 2 :  \n   \\[\n   4 \\times 2 = 8\n   \\]\n\n3. **Division**  \n   On divise le produit par 3 :  \n   \\[\n   \\frac{8}{3}= 2,\\!666\\ldots\n   \\]\n\n**Résultat**  \n\\[\n(2+2)\\times2/3 = \\frac{8}{3} \\approx 2,6667\n\\]\n\nDonc le calcul donne \\( \\displaystyle \\frac{8}{3} \\) (en décimal, environ\u202f2,67).",
                refusal=None,
                role="assistant",
                annotations=None,
                audio=None,
                function_call=None,
                tool_calls=None,
                reasoning_content='The user asks in French: "Quel est le résultat de (2+2)*2/3 ? Explique les étapes du calcul". Simple arithmetic: (2+2)=4, then *2 = 8, then /3 = 8/3 ≈ 2.6666667. Provide steps. Should output French answer.',
            ),
            provider_specific_fields={"stop_reason": None, "token_ids": None},
        )
    ],
    created=1763124653,
    model="hosted_vllm/gpt-oss-120b",
    object="chat.completion",
    service_tier=None,
    system_fingerprint=None,
    usage=CompletionUsage(
        completion_tokens=249,
        prompt_tokens=89,
        total_tokens=338,
        completion_tokens_details=None,
        prompt_tokens_details=None,
    ),
)
#Raisonnement Bas
Result: ChatCompletion(
    id="chatcmpl-eebfabf403c44a9db7fa568a11597513",
    choices=[
        Choice(
            finish_reason="stop",
            index=0,
            logprobs=None,
            message=ChatCompletionMessage(
                content="**Calcul\u202f: \\((2+2)\\times 2 \\div 3\\)**  \n\n1. **Parenthèses** – On commence toujours par les opérations à l’intérieur des parenthèses.  \n   \\[\n   2+2 = 4\n   \\]\n\n2. **Remplacer** le résultat dans l’expression :  \n   \\[\n   (2+2)\\times 2 \\div 3 \\;=\\; 4 \\times 2 \\div 3\n   \\]\n\n3. **Multiplication** – On effectue la multiplication avant la division (les deux ont la même priorité mais on lit de gauche à droite).  \n   \\[\n   4 \\times 2 = 8\n   \\]\n\n4. **Division** – On divise le résultat obtenu par 3.  \n   \\[\n   8 \\div 3 = \\frac{8}{3} \\approx 2{,}666\\overline{6}\n   \\]\n\n---\n\n### Résultat\n\n\\[\n\\boxed{\\dfrac{8}{3}\\;\\text{ou}\\;2,\\!666\\ldots}\n\\]\n\nLe résultat exact est la fraction \\(\\frac{8}{3}\\); en décimal, c’est \\(2,666\\ldots\\) (un 6 récurrent).",
                refusal=None,
                role="assistant",
                annotations=None,
                audio=None,
                function_call=None,
                tool_calls=None,
                reasoning_content="We need answer in French. Provide steps.",
            ),
            provider_specific_fields={"stop_reason": None, "token_ids": None},
        )
    ],
    created=1763124655,
    model="hosted_vllm/gpt-oss-120b",
    object="chat.completion",
    service_tier=None,
    system_fingerprint=None,
    usage=CompletionUsage(
        completion_tokens=294,
        prompt_tokens=89,
        total_tokens=383,
        completion_tokens_details=None,
        prompt_tokens_details=None,
    ),
)
#Raisonnement Moyen
Result: ChatCompletion(
    id="chatcmpl-e9f8d56ba9e048e6b34af8fb4efd9dc9",
    choices=[
        Choice(
            finish_reason="stop",
            index=0,
            logprobs=None,
            message=ChatCompletionMessage(
                content="**Calcul\u202f: \\((2+2)\\times2\\div3\\)**  \n\n1. **Parenthèses** – on résout d’abord ce qui se trouve entre les parenthèses :  \n   \\[\n   2+2 = 4\n   \\]\n\n2. **Multiplication** – on multiplie le résultat précédent par\u202f2 :  \n   \\[\n   4 \\times 2 = 8\n   \\]\n\n3. **Division** – on divise ensuite par\u202f3 :  \n   \\[\n   8 \\div 3 = \\frac{8}{3}\n   \\]\n\n4. **Résultat** – \\(\\frac{8}{3}\\) peut être exprimé :\n   - sous forme de fraction\u202f: \\(\\displaystyle \\frac{8}{3}\\)\n   - sous forme décimale approximative : \\(2,666\\ldots\\) (c’est‑à‑dire \\(2\\)\u202fet\u202f\\(2/3\\)).\n\n**Donc, \\((2+2)\\times2\\div3 = \\frac{8}{3} \\approx 2,67\\).**",
                refusal=None,
                role="assistant",
                annotations=None,
                audio=None,
                function_call=None,
                tool_calls=None,
                reasoning_content='User asks in French: "What is the result of (2+2)*2/3? Explain the steps of the calculation". So answer in French, give result, show steps. Compute: (2+2)=4, then *2 = 8, then /3 = 8/3 = 2.666..., exact fraction 8/3. Provide explanation.\n\nWe comply.',
            ),
            provider_specific_fields={"stop_reason": None, "token_ids": None},
        )
    ],
    created=1763124656,
    model="hosted_vllm/gpt-oss-120b",
    object="chat.completion",
    service_tier=None,
    system_fingerprint=None,
    usage=CompletionUsage(
        completion_tokens=330,
        prompt_tokens=89,
        total_tokens=419,
        completion_tokens_details=None,
        prompt_tokens_details=None,
    ),
)
#Raisonnement Haut
Result: ChatCompletion(
    id="chatcmpl-54c9d7e8dbec4ec89403dfeeaffb0ecd",
    choices=[
        Choice(
            finish_reason="stop",
            index=0,
            logprobs=None,
            message=ChatCompletionMessage(
                content="**Calcul étape par étape**\n\nL’expression à évaluer est :\n\n\\[\n(2+2)\\times 2 \\div 3\n\\]\n\n1. **Parenthèses** – on commence par ce qui est entre parenthèses  \n   \\[\n   2+2 = 4\n   \\]\n\n2. **Multiplication** – on multiplie le résultat de la parenthèse par 2  \n   \\[\n   4 \\times 2 = 8\n   \\]\n\n3. **Division** – on divise le produit obtenu par 3  \n   \\[\n   8 \\div 3 = \\frac{8}{3}\n   \\]\n\n   - En forme décimale, \\(\\frac{8}{3} = 2{,}666\\ldots\\) (la décimale 6 se répète indéfiniment).\n   - En forme mixte, \\(\\frac{8}{3} = 2\\frac{2}{3}\\).\n\n**Résultat** :  \n\n\\[\n(2+2)\\times 2 \\div 3 = \\frac{8}{3} \\approx 2{,}666\\ldots\n\\]",
                refusal=None,
                role="assistant",
                annotations=None,
                audio=None,
                function_call=None,
                tool_calls=None,
                reasoning_content='The user asks in French: "Quel est le résultat de (2+2)*2/3 ? Explique les étapes du calcul". The user wants the result of (2+2)*2/3, explain steps.\n\nWe must provide calculation steps. Also obey the guidelines: The request is straightforward arithmetic. So we can answer: compute: parentheses: 2+2 = 4. Then multiply by 2 => 4*2 = 8. Then divide by 3 => 8/3 = 2.666..., if simplified fraction 8/3. Provide steps in French.\n\nWe also can optionally discuss potential mixed numbers: 2+2=4, then 4*2=8, then 8/3 = 2 remainder 2 => 2 + 2/3. Provide decimal approximation.\n\nWe can talk about order of operations: parentheses, multiplication/division left to right.\n\nTherefore answer: The result is 8/3 ≈ 2,6667.\n\nWe should abide by user language. Provide step-by-step explanation, maybe demonstration.\n\nPotential handling: Might also discuss rational numbers: 8/3.\n\nThus answer: Le résultat is 8/3 (approx 2.666...). Steps: parentheses then multiplication then division.\n\nAlright.\n\nNow we must produce final output.',
            ),
            provider_specific_fields={"stop_reason": None, "token_ids": None},
        )
    ],
    created=1763124658,
    model="hosted_vllm/gpt-oss-120b",
    object="chat.completion",
    service_tier=None,
    system_fingerprint=None,
    usage=CompletionUsage(
        completion_tokens=530,
        prompt_tokens=89,
        total_tokens=619,
        completion_tokens_details=None,
        prompt_tokens_details=None,
    ),
)
```

Ces modèles ont une partie réflexion permettant des calculs plus exacts en général.

### 2.7 Conversation multi-tours[​](#27-conversation-multi-tours "Lien direct vers 2.7 Conversation multi-tours")

Dans ce code nous bouclons sur 3 appels à l'API, mais un rappel du contexte en fournissant le début de l'échange à chaque nouvel appel API permet à l'IA de répondre comme dans une conversation.

```python
# Exemple de conversation avec contexte
def chat_conversation():
    messages = [
        {"role": "system", "content": "Tu es un professeur de mathématiques patient et pédagogue. Tu expliques les choses en quelques phrases en vulgarisant."}
    ]

    questions = [
        "Qu'est-ce qu'une fonction linéaire ?",
        "Peux-tu me donner un exemple concret ?",
        "Comment représenter graphiquement cette fonction ?"
    ]

    for question in questions:
        # Ajouter la question de l'utilisateur
        messages.append({"role": "user", "content": question})

        try:
            response = client.chat.completions.create(
                model="mistral-small-3.2-24b",
                messages=messages,
                max_tokens=500,
                temperature=0.3
            )

            # Ajouter la réponse de l'assistant au contexte
            assistant_response = response.choices[0].message.content
            messages.append({"role": "assistant", "content": assistant_response})

            print(f"Q: {question}")
            print(f"R: {assistant_response}\n")

        except Exception as e:
            print(f"Erreur : {e}")
            break

# Lancer la conversation
chat_conversation()
```

**Résultat :**

```text
Q: Qu'est-ce qu'une fonction linéaire ?
R: Une fonction linéaire est une fonction mathématique qui suit une règle très simple : elle multiplie toujours son entrée par un nombre fixe, appelé le coefficient directeur. Imagine que tu as une machine à multiplier : peu importe le nombre que tu mets dedans, la machine le multiplie toujours par le même nombre. Par exemple, si la machine multiplie par 3, alors 2 devient 6, 5 devient 15, et ainsi de suite. En termes mathématiques, cela s'écrit souvent comme \( f(x) = kx \), où \( k \) est le coefficient directeur et \( x \) est l'entrée de la fonction.

Q: Peux-tu me donner un exemple concret ?
R: Bien sûr ! Prenons un exemple concret avec une fonction linéaire du quotidien : le calcul du prix total d'achat de plusieurs objets identiques.

Supposons que tu veuilles acheter des pommes. Chaque pomme coûte 2 euros. Le prix total dépend du nombre de pommes que tu achètes. Si tu achètes 1 pomme, tu paies 2 euros. Si tu achètes 2 pommes, tu paies 4 euros, et ainsi de suite.

Ici, la fonction linéaire est \( f(x) = 2x \), où \( x \) est le nombre de pommes et \( f(x) \) est le prix total. Le coefficient directeur est 2, ce qui représente le prix d'une seule pomme.

Tu vois, c'est comme une machine à multiplier : peu importe le nombre de pommes que tu mets dedans, la machine multiplie toujours par 2 pour te donner le prix total.

Q: Comment représenter graphiquement cette fonction ?
R: Pour représenter graphiquement la fonction linéaire \( f(x) = 2x \), tu peux suivre ces étapes simples :

1. **Choisis un système de coordonnées** : Dessine deux axes perpendiculaires. L'axe horizontal (axe des abscisses) représente les valeurs de \( x \) (le nombre de pommes), et l'axe vertical (axe des ordonnées) représente les valeurs de \( f(x) \) (le prix total).

2. **Trouve deux points** : Calcule quelques valeurs de \( f(x) \) pour différentes valeurs de \( x \). Par exemple :
   - Si \( x = 0 \), alors \( f(0) = 2 \times 0 = 0 \). Tu as le point (0, 0).
   - Si \( x = 1 \), alors \( f(1) = 2 \times 1 = 2 \). Tu as le point (1, 2).
   - Si \( x = 2 \), alors \( f(2) = 2 \times 2 = 4 \). Tu as le point (2, 4).

3. **Trace la droite** : Place ces points sur le graphique et trace une droite qui passe par ces points. Cette droite représente la fonction linéaire \( f(x) = 2x \).

La droite passera toujours par l'origine (0, 0) et aura une pente de 2, ce qui signifie qu'elle monte de 2 unités sur l'axe des ordonnées pour chaque unité que tu avances sur l'axe des abscisses.
```

---

## 3. Paramètres avancés en pratique[​](#3-paramètres-avancés-en-pratique "Lien direct vers 3. Paramètres avancés en pratique")

### 3.1 Contrôle précis de la génération[​](#31-contrôle-précis-de-la-génération "Lien direct vers 3.1 Contrôle précis de la génération")

```python
# Exemple avec paramètres avancés
try:
    response = client.chat.completions.create(
        model="mistral-small-3.2-24b",
        messages=[
            {
                "role": "user",
                "content": "Généère une liste de 5 conseils pour apprendre le Python. Indique FIN quand tu as terminé"
            }
        ],
        max_tokens=400,
        temperature=0.7,      # Créativité (0.0 = déterministe, 1.0 = très créatif)
        top_p=0.9,           # Nucleus sampling
        frequency_penalty=0.1, # Pénalité de répétition
        presence_penalty=0.1,  # Pénalité de présence
        stop=["---", "FIN"]    # Séquences d'arrêt
    )

    print(response.choices[0].message.content)

except Exception as e:
    print(f"Erreur : {e}")
```

**Résultat :**

```text
Voici 5 conseils pour apprendre le Python efficacement :

1. **Commencez par les bases** : Maîtrisez les concepts fondamentaux comme les variables, les boucles, les conditions et les fonctions avant de passer à des sujets plus avancés.
2. **Pratiquez régulièrement** : Appliquez ce que vous apprenez en résolvant des exercices, des projets simples ou en participant à des défis de programmation.
3. **Utilisez des ressources adaptées** : Choisissez des tutoriels, des livres ou des cours en ligne (comme *Python pour les Nuls*, Codecademy ou Real Python) qui correspondent à votre niveau.
4. **Lisez et analysez du code** : Étudiez des projets open source ou du code écrit par d'autres pour comprendre différentes approches et bonnes pratiques.
5. **Rejoignez une communauté** : Participez à des forums (Stack Overflow, Reddit) ou des groupes pour poser des questions et échanger avec d'autres apprenants.
```

### 3.2 Gestion des erreurs et retry[​](#32-gestion-des-erreurs-et-retry "Lien direct vers 3.2 Gestion des erreurs et retry")

Pour ce cas particulier, nous allons déclarer notre client avec une option en plus : `max_retries=0`
Cela afin de pouvoir faire démonstration de la gestion d'erreurs de timeout manuellement et non avec celle intégrée par défaut avec le package Python OpenAI.

Afin d'atteindre plus facilement ma limite d'utilisation pour cet exemple, je vais ici aussi définir volontairement une limite à la clé utilisée à 1 requête par minute sur l'API. Vos limites réelles serons certainement plus élevées.

```python
from openai import OpenAI

# Configuration du client pour notre API
client = OpenAI(
    api_key="sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    base_url="https://romeogate.univ-reims.fr/llm",
    max_retries=0
)
```
```python
import time
from openai import OpenAI

def generate_with_retry(client, messages, model="mistral-small-3.2-24b", max_retries=10):
    """Génération avec retry automatique en cas d'erreur"""
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=200,
                temperature=0.7,
                timeout=5
            )
            return response.choices[0].message.content

        except Exception as e:
            print(f"Tentative {attempt + 1} échouée : {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Backoff exponentiel
            else:
                raise e

# Utilisation
try:
    result = generate_with_retry(
        client,
        [{"role": "user", "content": "Explique brièvement le machine learning"}]
    )
    print("Résultat :", result)
except Exception as e:
    print(f"Échec définitif : {e}")
```

Voici comment se comporte le code dans ce cas :

```text
Tentative 1 échouée : Error code: 429 - {'error': {'message': 'LiteLLM Rate Limit Handler for rate limit type = key. Crossed TPM / RPM / Max Parallel Request Limit. current rpm: 1, rpm limit: 1, current tpm: 210, tpm limit: 200, current max_parallel_requests: 0, max_parallel_requests: 9223372036854775807', 'type': 'None', 'param': 'None', 'code': '429'}}
Tentative 2 échouée : Error code: 429 - {'error': {'message': 'LiteLLM Rate Limit Handler for rate limit type = key. Crossed TPM / RPM / Max Parallel Request Limit. current rpm: 1, rpm limit: 1, current tpm: 210, tpm limit: 200, current max_parallel_requests: 0, max_parallel_requests: 9223372036854775807', 'type': 'None', 'param': 'None', 'code': '429'}}
Tentative 3 échouée : Error code: 429 - {'error': {'message': 'LiteLLM Rate Limit Handler for rate limit type = key. Crossed TPM / RPM / Max Parallel Request Limit. current rpm: 1, rpm limit: 1, current tpm: 210, tpm limit: 200, current max_parallel_requests: 0, max_parallel_requests: 9223372036854775807', 'type': 'None', 'param': 'None', 'code': '429'}}
Tentative 4 échouée : Error code: 429 - {'error': {'message': 'LiteLLM Rate Limit Handler for rate limit type = key. Crossed TPM / RPM / Max Parallel Request Limit. current rpm: 1, rpm limit: 1, current tpm: 210, tpm limit: 200, current max_parallel_requests: 0, max_parallel_requests: 9223372036854775807', 'type': 'None', 'param': 'None', 'code': '429'}}
Tentative 5 échouée : Error code: 429 - {'error': {'message': 'LiteLLM Rate Limit Handler for rate limit type = key. Crossed TPM / RPM / Max Parallel Request Limit. current rpm: 1, rpm limit: 1, current tpm: 210, tpm limit: 200, current max_parallel_requests: 0, max_parallel_requests: 9223372036854775807', 'type': 'None', 'param': 'None', 'code': '429'}}
Résultat : Le **machine learning** (apprentissage automatique) est une branche de l'**intelligence artificielle (IA)** qui permet aux machines d'apprendre à partir de données sans être explicitement programmées. L'objectif est d'améliorer leurs performances sur une tâche donnée en identifiant des **modèles** (patterns) dans les données.

### Principaux concepts :
1. **Données** : Ensemble d'exemples (ex : images, textes, chiffres) utilisés pour entraîner le modèle.
2. **Algorithmes** : Règles mathématiques permettant au modèle d'apprendre (ex : régression, forêts aléatoires, réseaux de neurones).
3. **Entraînement** : Phase où le modèle ajuste ses paramètres pour minimiser les erreurs sur les données.
4. **Généralisation** : Capacité du modèle à bien fonctionner sur de nouvelles données (non vues pendant l'entraînement).

### Types d'apprentissage :
- **Supervis...
```

Nous pouvons voir ici que tant que nous avons atteint le quota de notre clé API, le code boucle (avec un maximum définit ici à 10), et dès que nous passons à la minute suivante et avons de nouveau le droit d'utiliser l'API, nous obtenons une réponse.

---

## 4. Pour aller plus loin[​](#4-pour-aller-plus-loin "Lien direct vers 4. Pour aller plus loin")

### 4.1 Modèles avec capacités visuelles[​](#41-modèles-avec-capacités-visuelles "Lien direct vers 4.1 Modèles avec capacités visuelles")

Certains modèles supportent l'analyse d'images. Voici comment envoyer une image : J'ai donné lors de l’exécution de cet exemple une image de la Joconde:

```python
# Exemple avec un modèle vision (ex: mistral-small-3.2)
import base64

# Encoder l'image en base64
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

# Utilisation
base64_image = encode_image("/home/monuser/Mona_Lisa.jpg")

response = client.chat.completions.create(
    model="mistral-small-3.2-24b",
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Que vois-tu dans cette image ?"
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                }
            ]
        }
    ],
    max_tokens=300
)

print(response.choices[0].message.content)
```

Il faut noter que cela ne fonctionne qu'avec des modèles LLM disposants de capacités de vision, tel que Mistral-Small-3.2.

**Résultat :**

```text
L'image représente la célèbre peinture "La Joconde" ou "Mona Lisa", réalisée par Léonard de Vinci. Voici une description détaillée :

1. **Sujet** : La peinture montre une femme assise, connue pour son sourire énigmatique. Elle est souvent identifiée comme Lisa Gherardini, une Florentine dont le mari, Francesco del Giocondo, aurait commandé le portrait.

2. **Posture et expression** : La femme est assise de trois quarts, les mains croisées devant elle. Son expression est calme et légèrement souriante, ce qui a contribué à la renommée de l'œuvre.

3. **Vêtements** : Elle porte une robe sombre avec un décolleté arrondi et des manches ajustées. Un voile léger couvre ses épaules et ses cheveux.

4. **Arrière-plan** : L'arrière-plan est un paysage flou avec des montagnes, des rivières et des ponts, typique du style sfumato de Léonard de Vinci. Ce paysage donne une impression de profondeur et de mystère.

5. **Technique** : La peinture est réalisée avec la technique du sfumato, qui utilise des nuances subtiles et des transitions douces entre les couleurs et les tons, créant une atmosphère douce et réaliste.

6. **Cadre** : La peinture est encadrée dans un cadre sombre, mettant en valeur les détails et les couleurs de l'œuvre.
```

### 4.2 Traitement de fichiers simple via l'API[​](#42-traitement-de-fichiers-simple-via-lapi "Lien direct vers 4.2 Traitement de fichiers simple via l'API")

#### Upload et analyse de documents texte[​](#upload-et-analyse-de-documents-texte "Lien direct vers Upload et analyse de documents texte")

Nous réalisons ici un ajout simple d'un document texte complet dans la requête envoyée au modèle.

```python
# Lecture et analyse d'un fichier texte
def analyze_document(file_path, question):
    with open(file_path, 'r', encoding='utf-8') as file:
        document_content = file.read()

    # Limiter la taille si nécessaire (selon le contexte du modèle)
    if len(document_content) > 8000:  # Environ 2000 tokens
        document_content = document_content[:8000] + "..."

    response = client.chat.completions.create(
        model="mistral-small-3.2-24b",
        messages=[
            {
                "role": "system",
                "content": "Tu es un assistant d'analyse de documents. Réponds aux questions en te basant sur le contenu fourni."
            },
            {
                "role": "user",
                "content": f"Document à analyser :\n\n{document_content}\n\nQuestion : {question}"
            }
        ],
        max_tokens=500,
        temperature=0.3
    )

    return response.choices[0].message.content

# Utilisation
result = analyze_document("/home/monuser/rapport.txt", "Quels sont les points clés de ce rapport ?")
print(result)
```

Fichier donné en input :

```markdown
# Rapport de Réunion – Atelier du Père Noël

**Date :** 12 septembre 2025
**Lieu :** Pôle Nord, Salle des Lutins « Grande Ourse »

**Présents :**
- Père Noël (Président)
- Mère Noël (Conseillère en Organisation et Restauration)
- Capitaine Lutin Bob (Chef de Production)
- Lutin Chef Tinker (Innovation et Jouets)
- Lutin Logistique Sparkle (Transport et Inventaire)
- Lutin Communication Jingle (Relations publiques, lettres et courrier magique)
- Lutin Sécurité Frosty (Sécurité du Pôle Nord et traîneau)
- Lutin Décor Lumina (Ambiance, décorations et emballage)
- Assistant Magique Twinkle (Support informatique et listes magiques)

---

## Ordre du jour
1. Bilan des préparatifs généraux
2. Production et répartition des jouets
3. Gestion des rennes et de la tournée
4. Innovations technologiques pour Noël
5. Logistique, emballage et livraison
6. Sécurité et confidentialité
7. Bien-être des lutins
8. Questions diverses

---

## 1. Bilan des préparatifs
- Père Noël souligne que 93 % des listes d’enfants sages sont finalisées.
- Twinkle rapporte que 7 % des adresses sont manquantes ou ambiguës ; action : contact magique prioritaire.
- Problème détecté : pénurie de chaussettes rouges et de ficelle dorée. Décision : approvisionnement d’urgence avec fournisseurs magiques.
- Mère Noël propose un calendrier de pauses chocolat chaud pour réduire le stress des lutins.

---

## 2. Production et répartition des jouets
- Tinker présente un rapport sur la production : puzzles, LEGO, poupées et nouveaux kits science magique.
- Décision : doublement de l’équipe sur puzzles et kits science.
- Bob propose un roulement pour éviter le burn-out, à mettre en place dès le 15 septembre.
- Lumina suggère une équipe spéciale pour les emballages « cadeaux personnalisés » avec autocollants magiques.

---

## 3. Gestion des rennes et planification de la tournée
- Sparkle confirme l’état des rennes : Rudolph nécessite un entraînement supplémentaire.
- Frosty propose un protocole météo pour éviter les tempêtes surprises.
- Calendrier de la tournée : tests des parcours longs et urbains prévus du 1er au 10 décembre.
- Nouveau traîneau expérimental (électrique/hybride) : test le 1er octobre avec Frosty en superviseur.

---

## 4. Innovations technologiques
- Tinker présente les prototypes : traîneau électrique, drones de repérage, et bracelet magique pour suivre le niveau de fatigue des lutins.
- Jingle propose un “chat magique” interactif pour informer les enfants de l’avancée de la distribution.
- Twinkle recommande l’intégration d’une base de données magique centralisée pour éviter les doublons de cadeaux.

---

## 5. Logistique, emballage et livraison
- Lumina insiste sur l’importance de l’emballage résistant aux intempéries polaires.
- Sparkle présente un plan de stockage optimisé par zones : jouets fragiles, volumineux, surprises.
- Décision : mise en place d’une équipe “express” pour les commandes urgentes ou erreurs dans la liste.

---

## 6. Sécurité et confidentialité
- Frosty rappelle : aucun lutin ne doit divulguer la liste des cadeaux ni les adresses.
- Mise en place de mots de passe magiques pour toutes les bases de données.
- Tinker propose des alarmes lumineuses pour le stockage des jouets de grande valeur.

---

## 7. Bien-être des lutins
- Mère Noël rappelle que les pauses chocolat chaud et biscuits sont obligatoires.
- Jingle propose des sessions de chant de Noël pour réduire le stress.
- Décision : concours interne de blagues de lutins pour renforcer l’esprit d’équipe.

---

## 8. Questions diverses
- Problème soulevé : certains lutins se plaignent de l’éclairage polaire trop intense. Solution : rideaux magiques ajustables.
- Bob mentionne qu’un lutin a accidentellement repeint le traîneau en vert fluo. Décision : repeindre avant le test.
- Père Noël conclut : « Chaque sourire compte. Même un lutin fatigué mérite son chocolat chaud. »

---

## Décisions majeures
1. Augmentation temporaire de la production de jouets de 20 %.
2. Test du traîneau électrique le 1er octobre.
3. Rotation stricte des équipes pour éviter le burn-out.
4. Rappel général sur la confidentialité et sécurité des listes.
5. Approvisionnement immédiat en chaussettes rouges et ficelle dorée.
6. Mise en place de divertissements et pauses pour le bien-être des lutins.

---

**Prochaine réunion :** 10 octobre 2025, Salle des Lutins « Grande Ourse »

**Clôture :** Père Noël remercie tous les lutins et insiste sur l’importance de l’esprit de Noël et de la magie.
```

**Résultat :**

```markdown
Voici les points clés du rapport de réunion de l'Atelier du Père Noël :

1. **Bilan des préparatifs généraux :**
   - 93 % des listes d’enfants sages sont finalisées.
   - 7 % des adresses sont manquantes ou ambiguës, nécessitant un contact magique prioritaire.
   - Pénurie de chaussettes rouges et de ficelle dorée, avec une décision d'approvisionnement d'urgence.
   - Proposition d'un calendrier de pauses chocolat chaud pour réduire le stress des lutins.

2. **Production et répartition des jouets :**
   - Présentation des rapports sur la production de puzzles, LEGO, poupées et nouveaux kits science magique.
   - Décision de doubler l’équipe sur puzzles et kits science.
   - Proposition d'un roulement pour éviter le burn-out.
   - Suggestion d'une équipe spéciale pour les emballages « cadeaux personnalisés » avec autocollants magiques.

3. **Gestion des rennes et planification de la tournée :**
   - Confirmation de l’état des rennes, avec un entraînement supplémentaire pour Rudolph.
   - Proposition d'un protocole météo pour éviter les tempêtes surprises.
   - Calendrier de la tournée avec tests des parcours longs et urbains prévus du 1er au 10 décembre.
   - Test d'un nouveau traîneau expérimental (électrique/hybride) le 1er octobre.

4. **Innovations technologiques :**
   - Présentation des prototypes : traîneau électrique, drones de repérage, et bracelet magique pour suivre le niveau de fatigue des lutins.
   - Proposition d’un “chat magique” interactif pour informer les enfants de l’avancée de la distribution.
   - Recommandation d’une base de données magique centralisée pour éviter les doublons de cadeaux.

5. **Logistique, emballage et livraison :**
   - Insistance sur l’importance de l’emballage résistant aux intempéries polaires.
   - Présentation d'un plan de stockage optimisé par zones.
   - Décision de mettre en place d’une équipe “express” pour les commandes urgentes ou erreurs dans la liste.

6. **Sécurité et confidentialité :**
   - Rappel de la confidentialité des listes de cadeaux et des adresses.
```

### 4.3 Traitement de fichiers via l'API et système RAG[​](#43-traitement-de-fichiers-via-lapi-et-système-rag "Lien direct vers 4.3 Traitement de fichiers via l'API et système RAG")

Nous allons utiliser ici un système dit 'RAG' simple pour chercher des informations dans notre document.
Le RAG va découper le document en petits morceaux (chunk), et en créer des 'vecteurs'.
Ces vecteurs serons ensuite comparés au vecteur de la question, et les chunks les plus proches (=normalement les plus pertinents) serons envoyés au LLM pour qu'il réponde en connaissant ces informations.

Je vais utiliser le même fichier de rapport que dans l'exemple juste au dessus.

```python
from openai import OpenAI
import numpy as np
import textwrap

client = OpenAI(
    api_key="sk-xxxxxxxxxxxxxxxxxxxxxxxxxx",
    base_url="https://romeogate.univ-reims.fr/llm/",
)

EMBED_MODEL = "Qwen3-Embedding-0.6B"
CHAT_MODEL = "mistral-small-3.2-24b"

# --- 1) Chargement du document ---
path = "/home/monhome/rapport.txt"
with open(path, "r", encoding="utf-8") as f:
    document = f.read()

print("Document chargé ! Longueur :", len(document), "caractères")

# --- 2) Découpage en chunks (200 caractères, peut être ajusté en fonction de la forme du document) ---
chunks = textwrap.wrap(document, 200)
print(f"{len(chunks)} chunks créés.")

# --- 3) Embeddings ---
def embed_texts(list_of_texts):
    response = client.embeddings.create(
        model=EMBED_MODEL,
        input=list_of_texts
    )
    return [np.array(item.embedding) for item in response.data]

chunk_embeddings = embed_texts(chunks)

# --- 4) Similarité cosinus ---
def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

# --- 5) Récupération des N chunks les plus pertinents ---
def retrieve_top_chunks(query_embedding, top_n=3):
    scores = [cosine_similarity(query_embedding, ce) for ce in chunk_embeddings]
    ranked_idx = np.argsort(scores)[::-1][:top_n]
    print("Scores des chunks triés :", [scores[i] for i in ranked_idx])
    selected_chunks = [chunks[i] for i in ranked_idx]
    return selected_chunks

# --- 6) Fonction RAG pour poser une question ---
def ask_llm(question, top_n=3):
    query_embedding = embed_texts([question])[0]
    relevant_chunks = retrieve_top_chunks(query_embedding, top_n=top_n)
    context_text = "\n\n".join(relevant_chunks)

    system_prompt = (
        "Tu es un assistant d'analyse de documents. "
        "Réponds aux questions en te basant uniquement sur le contenu fourni."
    )
    user_prompt = f"""
Voici les extraits pertinents du compte-rendu :

\"\"\"{context_text}\"\"\"

Question : {question}
"""
    response = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )
    return response.choices[0].message.content

# --- 7) Analyse générale : points clés ---
general_question = "Analyse ce document. Quels sont les points clés de ce rapport en un paragraphe ?"
general_summary = ask_llm(general_question, top_n=6)

print("\n===== RÉSUMÉ DES POINTS CLÉS =====\n")
print(general_summary)

# --- 8) Question spécifique ---
specific_question = "Sur quoi Lumina insiste-t-elle ?"
specific_answer = ask_llm(specific_question, top_n=3)

print("\n===== QUESTION SPÉCIFIQUE =====\n")
print("Question :", specific_question)
print("Réponse :", specific_answer)

# --- 9) Question spécifique ---
specific_question = "Quelle est la date de la prochaine réunion ?"
specific_answer = ask_llm(specific_question, top_n=3)

print("\n===== QUESTION SPÉCIFIQUE =====\n")
print("Question :", specific_question)
print("Réponse :", specific_answer)
```

Cela nous donne :

```text
Document chargé ! Longueur : 4597 caractères
24 chunks créés.

Scores des chunks triés : [0.3632878637642266, 0.35733239397647754, 0.35724026020641714, 0.3570157351583983, 0.33785440109600684]
===== RÉSUMÉ DES POINTS CLÉS =====
Le rapport de réunion de l'Atelier du Père Noël, tenu le 12 septembre 2025, met en lumière plusieurs points clés. Tout d'abord, une pénurie de chaussettes rouges et de ficelle dorée a été détectée, nécessitant un approvisionnement d'urgence auprès de fournisseurs magiques. La Mère Noël propose également un calendrier de pauses chocolat chaud pour éviter le burn-out parmi les participants. Le Père Noël souligne que 93 % des listes d’enfants sages sont finalisées, tandis que l'Assistant Magique Twinkle signale que 7 % des adresses sont manquantes ou ambiguës, nécessitant un contact magique prioritaire. De plus, des rappels sur la confidentialité et la sécurité des listes ont été effectués, et la mise en place de divertissements est prévue. L'ordre du jour incluait également la production et la répartition des jouets, ainsi que la gestion des rennes et des traîneaux.

Scores des chunks triés : [0.45564811306355507, 0.3283849554095956, 0.3171574017781593]
===== QUESTION SPÉCIFIQUE =====
Question : Sur quoi Lumina insiste-t-elle ?
Réponse : Lumina insiste sur l'importance de la logistique, de l'emballage et de la livraison.

Scores des chunks triés : [0.5517537828962294, 0.3894550043371809, 0.3285499520885742]
===== QUESTION SPÉCIFIQUE =====
Question : Quelle est la date de la prochaine réunion ?
Réponse : La prochaine réunion est prévue pour le 10 octobre 2025.
```

Avec le RAG, on peut aller bien plus loin que la simple recherche dans des chunks d'un court texte que nous pourrions ici joindre en entier comme dans l'exemple précédant.

Par exemple :

- **Index vectoriel persistant** : stocker les embeddings dans FAISS ou Milvus pour rechercher instantanément dans de gros volumes de documents préalablement convertis en embeddings.
- **Découpage intelligent** : segmenter par sections, titres ou paragraphes plutôt que par longueur fixe, pour que le contexte soit plus précis.
- **Fusion de contexte** : combiner plusieurs chunks pertinents et même résumer avant de les envoyer au modèle pour éviter de dépasser la limite de tokens.
- **Recherche avancée** : filtrer par mots-clés, dates, auteurs, ou métadonnées pour ne considérer que les passages pertinents.

---

## 5. Dépannage[​](#5-dépannage "Lien direct vers 5. Dépannage")

### Erreurs courantes[​](#erreurs-courantes "Lien direct vers Erreurs courantes")

| Erreur | Cause probable | Solution |
| --- | --- | --- |
| `401 Unauthorized` | Clé API incorrecte | Vérifiez votre clé d'authentification |
| `404 Not Found` | Modèle inexistant | Utilisez `client.models.list()` pour voir les modèles disponibles |
| `429 Too Many Requests` | Limite de taux atteinte | Implémentez un système de retry avec délai |
| `500 Internal Server Error` | Erreur serveur | Réessayez plus tard, contactez l'administrateur |
| `Connection timeout` | Problème réseau | Vérifiez votre connexion internet |

### Support[​](#support "Lien direct vers Support")

Pour toute question ou problème technique :

- Contactez l'équipe technique du Centre de calcul ROMEO de l'Université de Reims ([romeo@univ-reims.fr](mailto:romeo@univ-reims.fr))

---

← [Interface Web Oratio](gui_oratio.md) | → [Modèles disponibles](models.md)
