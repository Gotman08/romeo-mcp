# `dataset_prepare`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `dataset_prepare`

_Préparer un téléchargement depuis un nœud de calcul._

**Profils :** `full`, `expert`.

**Effet :** Enregistre un plan local. Peut lire les racines par SSH ; aucune écriture ni soumission sur ROMEO.

## 🎯 Utilisation

Crée un plan pour une URL directe, un dépôt git ou un dataset Hugging Face. Le téléchargement sera exécuté par un job sur l’architecture choisie.

## ⚙️ Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `source` | `str` | Oui | — | URL directe, URL git ou identifiant ORGANISATION/DATASET de Hugging Face. |
| `destination` | `str` | Oui | — | Chemin distant où déposer les données. |
| `kind` | `str` | Non | `"auto"` | Type de source : auto, url, git ou huggingface. |
| `minutes` | `int` | Non | `60` | Durée demandée en minutes, sauf si time_limit est fourni dans dataset_prepare. |
| `time_limit` | `str \| None` | Non | `null` | Durée maximale, par exemple 1m, 1h ou 2h. |
| `arch` | `str` | Non | `"x64cpu"` | Architecture cible : x64cpu ou armgpu. null laisse la préparation la déduire lorsque l’outil l’accepte. |
| `env_path` | `str \| None` | Non | `null` | Venv existant avec huggingface_hub, obligatoire pour kind=huggingface. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## ▶️ Exemple

Arguments JSON à transmettre à `dataset_prepare` depuis votre client MCP :

```json
{
  "source": "ORGANISATION/DATASET",
  "destination": "/scratch_p/VOTRE_IDENTIFIANT/datasets/exemple",
  "kind": "huggingface",
  "arch": "x64cpu",
  "env_path": "/scratch_p/VOTRE_IDENTIFIANT/venv-hf",
  "time_limit": "1h"
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## 📤 Résultat

Le type de source résolu, la destination, le script de téléchargement et le plan local.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## 📌 Prérequis et limites

Pour Hugging Face, fournir un venv de la même architecture avec huggingface_hub déjà installé. Aucun paquet n’est installé par le téléchargement ; time_limit remplace minutes lorsqu’il est renseigné.

## 🔗 Voir aussi

[`dataset_download`](dataset_download.md) · [`python_packages_prepare`](python_packages_prepare.md) · [`romeo_quota`](romeo_quota.md)

[Code de l’outil](../../romeo_mcp/outils_donnees.py#L349) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)
