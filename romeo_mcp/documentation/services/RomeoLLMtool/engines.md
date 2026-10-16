---
title: "Moteurs"
source: "https://romeo.univ-reims.fr/documentation/services/RomeoLLMtool/engines"
scraped_at: "2026-10-16 15:47:07"
---

[Sommaire](../../SOMMAIRE.md) › [Accueil](../../index.md) › [Services](../../services.md) › [RomeoLLMTool](../RomeoLLMtool.md) › Moteurs · [Corpus ROMEO](../../README.md) · [Guides MCP](https://github.com/Gotman08/romeo-mcp/blob/main/docs/README.md) · [Tools](https://github.com/Gotman08/romeo-mcp/blob/main/docs/Tools.md)

# Moteurs

Un moteur est le serveur qui fait réellement tourner un modèle. Une fiche en
choisit un avec `engine:` ; romeollmtool en connaît trois.

| Moteur | `engine:` | Pour |
| --- | --- | --- |
| **vLLM** | `vllm` | le moteur le plus complet ici : parallélisme tenseur et pipeline, multi-nœud (vLLM + Ray), vision, et des usages hors chat (TTS via le greffon `vllm-omni`, embeddings, classement de documents, transcription). |
| **SGLang** | `sglang` | alternative généraliste, avec son propre parallélisme tenseur et pipeline, GGUF compris. |
| **llama.cpp** (`llama-server`) | `llamaserver` | modèles GGUF quantifiés ; `n_gpu_layers` règle la part laissée au GPU (tout, par défaut), utile sur un modèle qui ne tient pas entièrement en mémoire GPU. Vision possible via `mmproj_file`. |

Le choix dépend du modèle visé : son format de poids (safetensors ou GGUF),
s'il a besoin de plusieurs nœuds, et des endpoints dont vous avez besoin
(simple chat, ou embeddings/classement/transcription/synthèse vocale). Les
clés exactes de chaque section de moteur sont détaillées dans
[Écrire une fiche](../../services/RomeoLLMtool/fiches#la-section-du-moteur.md).

## Moteurs partagés[​](#moteurs-partagés "Lien direct vers Moteurs partagés")

Les moteurs utilisables par tous sont construits et validés par les
administrateurs, dans `/apps/romeotools/llmvenvs/<moteur>-<version>/`. Une
fiche choisit sa version avec `version:` dans la section de son moteur
(`vllm.version: "0.29.0"`, par exemple). La liste est visible par
`romeollmtool engines` ou l'onglet Moteurs de l'interface :

| Colonne | Sens |
| --- | --- |
| ÉTAT | `prêt` si le moteur est complet et utilisable, `incomplet` sinon |
| VALIDÉ | un admin a confirmé que ce moteur fonctionne (`romeollmtool-admin validate-engine`) |
| CONSTRUIT | date de construction |

Si une fiche réclame un moteur absent de la liste ou marqué incomplet,
`launch` le signale avant de soumettre, avec la commande (réservée aux
administrateurs) qui le construirait.

## Variantes[​](#variantes "Lien direct vers Variantes")

Un modèle demande parfois un paquet Python absent du moteur standard (un
greffon, une dépendance propre à son architecture). Les administrateurs
construisent alors une **variante** : même moteur, version suffixée
(`0.29.0+cohere`, `0.29.0+omni`, `0.29.0+audio`…), avec ce paquet en plus,
sans toucher au moteur partagé existant. Une fiche qui en a besoin demande
cette version précise :

```yaml
vllm:
  version: "0.29.0+cohere"
```

Les variantes existantes apparaissent comme n'importe quelle autre version
dans `romeollmtool engines`. Construire une nouvelle variante est une
opération d'administration (`romeollmtool-admin build-venv`) ; en tant
qu'utilisateur, il suffit de savoir qu'une version avec un suffixe est un
moteur standard complété, pas un moteur à part.

## Votre propre moteur (`engine_dir:`)[​](#votre-propre-moteur-engine_dir "Lien direct vers votre-propre-moteur-engine_dir")

Une fiche perso peut aussi désigner **votre propre installation** d'un
moteur, à la place d'une version partagée, par exemple pour essayer une
version plus récente ou un moteur modifié, sans attendre une variante
construite par un administrateur. Cela se règle dans la fiche elle-même, avec
`engine_dir:` à la place de `version:` ; le job l'utilise tel quel, sans
l'installer ni le réparer.

La marche à suivre complète (ce que chaque moteur attend dans ce dossier, la
recette de construction sur un nœud de calcul, et les règles à respecter) est
détaillée dans [Écrire une fiche, « Fournir votre propre moteur »](../../services/RomeoLLMtool/fiches#fournir-votre-propre-moteur-engine_dir.md).

---

← [Écrire une fiche](fiches.md) | → [Utiliser l'API](api.md)

## Dans cette section

[↑ Haut de page](#moteurs) · [Sommaire officiel](../../SOMMAIRE.md) · [Guide du corpus](../../README.md)
