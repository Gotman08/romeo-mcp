# `python_packages_prepare`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `python_packages_prepare`

_Préparer l’installation de paquets dans un venv._

**Profils :** `full`, `expert`.

**Effet :** Enregistre un plan local. Peut lire les racines par SSH ; aucune écriture ni soumission sur ROMEO.

## 🎯 Utilisation

Crée le plan d’installation dans un environnement existant, sur la même architecture. Le script réutilise le dépôt local de roues binaires quand celles-ci sont disponibles.

## ⚙️ Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `env_path` | `str` | Oui | — | Chemin distant du venv de l’architecture cible. |
| `packages` | `list[str]` | Oui | — | Spécifications de paquets pip à installer, de 1 à 100 éléments. |
| `arch` | `str` | Non | `"armgpu"` | Architecture cible : x64cpu ou armgpu. null laisse la préparation la déduire lorsque l’outil l’accepte. |
| `time_limit` | `str` | Non | `"30m"` | Durée maximale, par exemple 1m, 1h ou 2h. |
| `upgrade` | `bool` | Non | `false` | Demander à pip la mise à jour des paquets sélectionnés. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## ▶️ Exemple

Arguments JSON à transmettre à `python_packages_prepare` depuis votre client MCP :

```json
{
  "env_path": "/scratch_p/VOTRE_IDENTIFIANT/venv",
  "packages": [
    "numpy"
  ],
  "arch": "x64cpu",
  "upgrade": false
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## 📤 Résultat

Le venv visé, le dépôt de roues, le script pip, les ressources et le plan local.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## 📌 Prérequis et limites

Fournir de 1 à 100 paquets et un venv correspondant à l’architecture du nœud. La préparation n’installe rien ; attendre la réussite du job d’installation avant d’utiliser les paquets.

## 🔗 Voir aussi

[`python_packages_install`](python_packages_install.md) · [`python_env_prepare`](python_env_prepare.md) · [`python_wheel_prepare`](python_wheel_prepare.md)

[Code de l’outil](../../romeo_mcp/outils_execution.py#L61) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)
