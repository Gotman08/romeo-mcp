# `python_wheel_prepare`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `python_wheel_prepare`

_Préparer la construction d’une roue Python._

**Profils :** `full`, `expert`.

**Effet :** Enregistre un plan local. Peut lire les racines par SSH ; aucune écriture ni soumission sur ROMEO.

## 🎯 Utilisation

Génère un job pip wheel pour une spécification de paquet ou une URL git+https. La roue sera placée dans le dépôt local associé à l’architecture cible.

## ⚙️ Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `source` | `str` | Oui | — | Spécification pip ou URL git+https du paquet à construire. |
| `arch` | `str` | Non | `"armgpu"` | Architecture cible : x64cpu ou armgpu. null laisse la préparation la déduire lorsque l’outil l’accepte. |
| `time_limit` | `str` | Non | `"45m"` | Durée maximale, par exemple 1m, 1h ou 2h. |
| `cpus_per_task` | `int` | Non | `32` | Nombre de cœurs réservés par tâche. |
| `with_gpu` | `bool` | Non | `false` | Réserver un GPU pour cette opération si sa construction ou son exécution en a besoin. |
| `spack_packages` | `list[str] \| None` | Non | `null` | Spécifications Spack à charger pour l’architecture du job. |
| `no_build_isolation` | `bool` | Non | `false` | Désactiver l’environnement de construction isolé de pip. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## ▶️ Exemple

Arguments JSON à transmettre à `python_wheel_prepare` depuis votre client MCP :

```json
{
  "source": "PAQUET_A_CONSTRUIRE",
  "arch": "armgpu",
  "time_limit": "45m",
  "cpus_per_task": 16
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## 📤 Résultat

Le script de construction, la source, le dépôt de roues, les ressources et le plan local.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## 📌 Prérequis et limites

La construction utilise --no-deps : préparer les dépendances séparément. no_build_isolation suppose que l’environnement de construction contient déjà les dépendances requises.

## 🔗 Voir aussi

[`python_wheel_build`](python_wheel_build.md) · [`python_packages_prepare`](python_packages_prepare.md) · [`romeo_software`](romeo_software.md)

[Code de l’outil](../../romeo_mcp/outils_execution.py#L72) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)
