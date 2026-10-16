---
title: "Écrire une fiche"
source: "https://romeo.univ-reims.fr/documentation/services/RomeoLLMtool/fiches"
scraped_at: "2026-10-16 15:47:07"
---

[Sommaire](../../SOMMAIRE.md) › [Accueil](../../index.md) › [Services](../../services.md) › [RomeoLLMTool](../RomeoLLMtool.md) › Écrire une fiche · [Corpus ROMEO](../../README.md) · [Guides MCP](https://github.com/Gotman08/romeo-mcp/blob/main/docs/README.md) · [Tools](https://github.com/Gotman08/romeo-mcp/blob/main/docs/Tools.md)

# Écrire une fiche

Une fiche est un fichier YAML qui décrit **un modèle et comment le servir**.
Posez la vôtre dans `~/.romeollmtool/configs/<nom>.yaml` : elle apparaît aussitôt
dans `romeollmtool catalog list` et dans l'onglet Catalogue, et se lance par
`romeollmtool launch <nom> --project-code <code>`. Le nom du fichier est
l'identifiant de la fiche. Le code projet, sur lequel le job est imputé, est
obligatoire (`--slurm-association` fait la même chose) ; l'interface le propose
dans une liste déroulante.

Deux sources, deux libertés :

|  | Catalogue (`catalog/`) | Vos fiches (`~/.romeollmtool/configs/`) |
| --- | --- | --- |
| Qui l'écrit | proposé par merge request, validé par un admin | vous |
| Modèle | déposé dans le dépôt partagé | dépôt partagé, `download_to:` ou chemin local |
| Moteur | version construite par les admins | idem, ou votre propre `engine_dir:` |
| Catégories | liste fermée (voir plus bas) | libres |
| Licence | `license:` et `license_usage:` obligatoires | facultatives |

Une fiche perso portant le même nom qu'une fiche du catalogue **complète** celle-ci :
vous ne redonnez que les clés à changer.

## Exemple complet[​](#exemple-complet "Lien direct vers Exemple complet")

```yaml
display_name: "Mon modèle (vLLM)"      # nom affiché ; défaut : le nom du fichier
description: "À quoi il sert."
category: [perso, creative]
engine: vllm                            # vllm, sglang ou llamaserver

download_to: /scratch_p/moi/rlt_models  # le job télécharge le modèle une fois ici

slurm:
  time: "24:00:00"                      # maximum 24:00:00
  gpus: 2                               # par nœud
  cpus: 32
  memory: "128G"
  constraint: "armgpu"                  # armgpu (GPU) ou x64cpu
  nodes: 1                              # > 1 : multi-nœud (vLLM + Ray)
  reservation: ""                       # facultatif

env:                                    # variables d'environnement du job
  PYTORCH_CUDA_ALLOC_CONF: "expandable_segments:True"

vllm:                                   # la section porte le nom du moteur
  version: "0.29.0"                     # moteur partagé (romeollmtool engines)
  model: "org/nom-du-modele"            # id HuggingFace ou chemin absolu
  tensor_parallel_size: 2
  extra_args:
    - "--gpu-memory-utilization"
    - "0.85"
    - "--max-model-len"
    - "131072"

generation:                             # valeurs par défaut des requêtes
  temperature: 1.0
  top_p: 0.95
  max_tokens: 8192
```

## Clés à la racine[​](#clés-à-la-racine "Lien direct vers Clés à la racine")

| Clé | Rôle |
| --- | --- |
| `engine` | **obligatoire** : `vllm`, `sglang` ou `llamaserver`. |
| `id` | identifiant ; par défaut le nom du fichier. |
| `display_name`, `description` | nom et phrase affichés. |
| `category` | liste ; libre pour une fiche perso. |
| `license`, `license_usage` | nom exact de la licence, et `open`, `conditional` ou `non-commercial`. |
| `verified`, `verified_note` | statut et sa raison ; voir « Validation ». |
| `verified_at`, `verified_by` | date et auteur de la validation, écrits automatiquement. |
| `slurm` | ressources demandées (voir ci-dessus). |
| `env` | variables d'environnement du job. |
| `generation` | valeurs par défaut des requêtes. |
| `download_to` | dossier où le job télécharge le modèle (fiches perso). |

Toute autre clé est refusée, pour attraper les fautes de frappe.

```yaml
id: mon-modele                       # sinon, nom du fichier
license: "Apache 2.0"
license_usage: open                  # open, conditional ou non-commercial
category: [reasoning, vision, long-context]   # catégories du catalogue : voir plus bas
```

`generation:` accepte `temperature`, `top_p`, `top_k`, `min_p`,
`repetition_penalty`, `presence_penalty` et `max_tokens`. Ces valeurs sont
appliquées par la gateway **sans jamais écraser** ce que le client demande
(voir [Utiliser l'API](../../services/RomeoLLMtool/api.md)).

```yaml
generation:
  temperature: 0.7
  top_p: 0.9
  top_k: 40
  min_p: 0.05
  repetition_penalty: 1.1
  presence_penalty: 0.0
  max_tokens: 4096
```

## La section du moteur[​](#la-section-du-moteur "Lien direct vers La section du moteur")

Elle porte le nom du moteur et contient au minimum `version:` (moteur partagé) ou
`engine_dir:` (votre propre installation), et `model:`. Pour une vue
d'ensemble des trois moteurs et de leurs variantes, voir
[Moteurs](../../services/RomeoLLMtool/engines.md).

`model:` accepte un identifiant HuggingFace (`org/nom`) ou un chemin absolu. Sans
`download_to:` ni chemin local, le modèle doit être dans le dépôt partagé.

**Communs aux trois moteurs** : `extra_args` (liste passée telle quelle au
serveur), `served_model_name` (nom exposé par l'API), `engine_dir`.

```yaml
vllm:
  version: "0.29.0"
  model: "org/nom-du-modele"
  served_model_name: "mon-modele"    # nom exposé par l'API ; défaut : model:
```

**vllm** : `tensor_parallel_size`, `pipeline_parallel_size`, `tokenizer`,
`gguf_file`, `quirks` (correctifs nommés pour un défaut connu de vLLM).
`download_patterns` (liste de motifs) limite le téléchargement à certains
fichiers du dépôt : utile quand un dépôt publie les mêmes poids sous deux formats,
comme les modèles Mistral (`consolidated*.safetensors` et `model-*.safetensors`).

```yaml
vllm:
  version: "0.29.0"
  model: "org/nom-du-modele"
  tensor_parallel_size: 2
  pipeline_parallel_size: 2          # multi-nœud : nodes > 1 dans slurm:
  tokenizer: "org/autre-tokenizer"   # si différent du modèle
  gguf_file: "modele-Q4_K_M.gguf"    # modèle servi en GGUF plutôt qu'en safetensors
  quirks: ["rope-null-layer-type"]   # correctif nommé, voir ci-dessous
  download_patterns:                 # fiche perso : limite le téléchargement
    - "model-*.safetensors"
    - "*.json"
```

`quirks:` demande un correctif nommé pour un défaut connu de vLLM qui, sans
lui, empêche un modèle précis de démarrer (par exemple, un paramétrage
d'encodage de position que vLLM refuse avant même de charger le modèle). Ce
n'est jamais appliqué par défaut, seulement si la fiche le demande, et un nom
inconnu est refusé : le message d'erreur donne alors la liste des correctifs
disponibles à cet instant. Un correctif disparaît (devient un nom inconnu)
dès que la version de vLLM concernée corrige le défaut d'origine.

> ⚠️ **Attention**
>
> remarque

Contrairement à une variante de moteur, un correctif n'est pas quelque chose
qu'un administrateur active à la demande : il est écrit dans le code de
romeollmtool lui-même. Si votre modèle a besoin d'un correctif qui n'existe
pas encore, c'est une évolution de l'outil à proposer par merge request sur
son dépôt, pas une commande à demander à un administrateur.

`omni: true` lance le modèle via le greffon vllm-omni (`vllm serve <modèle> --omni`) pour des endpoints hors chat, par exemple `/v1/audio/speech` (TTS).
Ne se combine pas avec `quirks:` ni avec `task:`.

```yaml
vllm:
  version: "0.29.0+omni"             # variante construite avec vllm-omni
  model: "org/modele-tts"
  omni: true
```

`task:` bascule un vLLM standard sur un autre type de serveur que la
génération de texte : `embed` (`/v1/embeddings`), `score` (classement de
documents, `/v1/score` et `/v1/rerank`) ou `transcription` (parole vers texte,
`/v1/audio/transcriptions`). `embed` et `score` ajoutent `--runner pooling`
(le `--task` historique de vLLM est deprecated) ; `transcription` n'ajoute
rien, un Whisper est reconnu à son architecture.

```yaml
vllm:
  version: "0.29.0"
  model: "Qwen/Qwen3-Embedding-4B"
  task: embed                        # embed, score ou transcription
```

`embed` et `score` tournent sur le vLLM standard, sans rien de plus.
`transcription`, lui, a besoin d'une variante vLLM avec le support audio
(voir [Moteurs, « Variantes »](../../services/RomeoLLMtool/engines#variantes.md)) ; sur le vLLM
standard, il échoue au démarrage plutôt qu'au premier fichier envoyé :

```yaml
vllm:
  version: "0.29.0+audio"            # variante avec le support audio
  model: "org/modele-whisper"
  task: transcription
```

Un modèle qui n'est pas nativement pooling (ex. Qwen/Qwen3-Reranker, pensé
pour être prompté en génération plutôt que classifié directement) a en plus
besoin d'un `--hf-overrides` dans `extra_args:` pour forcer son architecture
réelle (propre au modèle, voir sa fiche HuggingFace) :

```yaml
vllm:
  version: "0.29.0"
  model: "Qwen/Qwen3-Reranker-4B"
  task: score
  extra_args:
    - "--hf-overrides"
    - '{"architectures": ["Qwen3ForSequenceClassification"]}'
```

La fiche n'a alors ni chat ni streaming à tester : `romeollmtool verify`
appelle directement l'endpoint concerné. Ne se combine pas avec `omni:`.

**sglang** : `tp_size`, `pp_size`, `gguf_file`, `gguf_pattern`.

```yaml
sglang:
  version: "0.5.13"
  model: "org/nom-du-modele"
  tp_size: 2
  pp_size: 1
  gguf_file: "modele-Q4_K_M.gguf"       # pour servir un GGUF
  gguf_pattern: "modele-Q4_K_M-*.gguf"  # GGUF réparti en plusieurs fichiers
```

**llamaserver** : `gguf_file` (**obligatoire**), `gguf_pattern` (glob pour un GGUF
en plusieurs fichiers, ou liste de noms), `mmproj_file` (projecteur vision ;
comme `gguf_file`, un chemin dans le dépôt, sous-dossier compris),
`n_gpu_layers` (défaut −1 : tout sur GPU), `n_ctx`, `n_threads`,
`reasoning_format`, `chat_template`.

```yaml
llamaserver:
  version: "b11040"
  gguf_file: "modele-Q4_K_M.gguf"      # obligatoire
  mmproj_file: "mmproj-modele.gguf"    # projecteur vision, si le modèle en a besoin
  n_gpu_layers: -1                      # défaut : tout sur GPU
  n_ctx: 32768
  n_threads: 16
  reasoning_format: "deepseek"
  chat_template: "chatml"
```

## Fournir votre propre moteur (`engine_dir:`)[​](#fournir-votre-propre-moteur-engine_dir "Lien direct vers fournir-votre-propre-moteur-engine_dir")

Dans une fiche perso, `engine_dir:` remplace `version:` et désigne **votre**
installation du moteur, au lieu de celle construite par les admins. Utile pour
essayer une version plus récente, ou un moteur modifié. Réservé aux fiches
perso : une fiche du catalogue partagé qui la demande est refusée (elle doit
rester reproductible par tout le monde, donc s'appuyer uniquement sur les
moteurs et modèles partagés).

Le job ne l'installe pas et ne le répare pas : il l'utilise tel quel. Ce qu'il
attend, selon le moteur :

| Moteur | Ce que `engine_dir:` doit contenir |
| --- | --- |
| `vllm` | un environnement Python (`bin/python`, `bin/activate`) où `import vllm` fonctionne. |
| `sglang` | le même, où `import sglang` fonctionne. |
| `llamaserver` | `bin/llama-server` (exécutable) **et** `venv/bin/python`, ce dernier avec `huggingface_hub`. |

> ⚠️ **Warning**
>
> Trois règles à respecter

1. **Construisez-le sur un nœud de calcul**, jamais sur le nœud de connexion :
   les nœuds de calcul sont en aarch64, le nœud de connexion en x86\_64. Un
   environnement construit au mauvais endroit ne démarrera pas.
2. **Utilisez le même Python que le job** (`spack load python@3.13.0/rom`) et la
   même version de CUDA, sinon l'environnement s'active mais le moteur ne
   trouvera pas ses bibliothèques.
3. **Installez `huggingface_hub`** : les scripts du job s'en servent pour
   télécharger un modèle (`download_to:`) et pour les GGUF.

Recette, à lancer dans un job sur un nœud `armgpu` (c'est celle des moteurs
partagés) :

```bash
romeo_load_armgpu_env
spack load python@3.13.0/rom
spack load cuda@13.0.2/dvle736
CUDA_PREFIX=$(spack location -i cuda@13.0.2/dvle736)
export CUDA_HOME=${CUDA_PREFIX} LD_LIBRARY_PATH=${CUDA_PREFIX}/lib64:${LD_LIBRARY_PATH:-}

python3 -m venv /scratch_p/$USER/mon-vllm
/scratch_p/$USER/mon-vllm/bin/pip install --upgrade pip
/scratch_p/$USER/mon-vllm/bin/pip install "vllm==0.29.0" "ray[cgraph]" huggingface_hub \
    --extra-index-url https://download.pytorch.org/whl/cu130
```

puis dans la fiche :

```yaml
vllm:
  engine_dir: /scratch_p/moi/mon-vllm   # à la place de version:
  model: "org/nom-du-modele"
```

> ⚠️ **Warning**
>
> Protégez-le des autres

Ce dossier est exécuté dans vos jobs, donc sous votre compte. S'il est
modifiable par d'autres utilisateurs, ils peuvent y faire exécuter ce qu'ils
veulent en votre nom. Un `chmod -R go-w` sur le dossier suffit.

Avant de soumettre, l'outil vérifie que les fichiers attendus existent et
refuse le lancement en les nommant si l'un manque.

## Ce qui est refusé[​](#ce-qui-est-refusé "Lien direct vers Ce qui est refusé")

> ⚠️ **Attention**
>
> danger

- **Les secrets** : `api_key:` et `hf_token:` n'ont pas leur place dans une fiche.
  La clé du moteur est gérée par l'outil ; le token HuggingFace est lu dans
  `~/.romeollmtool/secrets/hf_token`.
- **Dans `extra_args`** : `--api-key` et assimilés (une clé en ligne de commande
  est lisible par les autres utilisateurs du nœud), ainsi que `--port` et
  `--host`, fixés par l'outil.
- **Une durée au-dessus de 24 h**, pour les jobs comme pour la gateway. Le
  contrôle se fait au lancement ou à la vérification, pas à la simple
  lecture de la fiche : `romeollmtool launch`/`verify` refusent de soumettre
  si `slurm.time:` dépasse 24:00:00 (message explicite, rien n'est soumis).
  L'interface, elle, propose déjà 24:00:00 par défaut si la fiche demande
  plus, pour éviter l'erreur.
- **Dans `env`** : les variables réservées aux clés (`VLLM_API_KEY`,
  `LLAMA_API_KEY`, `HF_TOKEN`…).

```yaml
# refusé, pour les raisons ci-dessus :
api_key: "sk-..."
hf_token: "hf_..."
slurm:
  time: "48:00:00"                 # au-dessus de 24:00:00
vllm:
  extra_args: ["--api-key", "sk-...", "--port", "8000"]
env:
  VLLM_API_KEY: "sk-..."
```

## Catégories du catalogue[​](#catégories-du-catalogue "Lien direct vers Catégories du catalogue")

`general`, `reasoning`, `vision`, `tools`, `long-context`, `moe`, `code`,
`embedding`, `ranking`, `stt`.
Une fiche perso range comme elle veut ; `vision` a un effet concret : la
vérification envoie alors une image au modèle.

## Vérification et validation[​](#vérification-et-validation "Lien direct vers Vérification et validation")

```bash
romeollmtool verify <fiche>     # lance un vrai job, teste, arrête, écrit un rapport
```

Les contrôles : refus sans clé, modèle exposé sous le bon nom, réponse à une
question simple, streaming, et image si la fiche est en catégorie `vision`.
Pour une fiche `vllm.task:` (embed/score/transcription) ou `vllm.omni:` (TTS),
les deux premiers contrôles sont les mêmes mais chat et streaming sont
remplacés par un appel direct à l'endpoint concerné (`/v1/embeddings`,
`/v1/rerank`, `/v1/audio/transcriptions` ou `/v1/audio/speech`).

`verified:` vaut `true`, `false` ou `experimental` :

- dans le **catalogue**, seul un admin le change, après un `verify` réussi ;
- dans **votre** fiche, `experimental` vous permet de signaler une réserve, avec
  `verified_note: "la raison"`, rappelée au lancement. `true` et `false` n'y ont
  pas de sens : une fiche perso s'affiche « — ».

```yaml
verified: experimental
verified_note: "fonctionne, lent en contexte long (plus de 100K tokens)."
```

Pour proposer une fiche au catalogue partagé : merge request ajoutant
`catalog/<fiche>.yaml` sur le dépôt du projet. Elle doit alors utiliser le moteur
et le modèle partagés, donc ni `download_to:` ni `engine_dir:`.

---

← [Ligne de commande](cli.md) | → [Moteurs](engines.md)

## Dans cette section

[↑ Haut de page](#écrire-une-fiche) · [Sommaire officiel](../../SOMMAIRE.md) · [Guide du corpus](../../README.md)
