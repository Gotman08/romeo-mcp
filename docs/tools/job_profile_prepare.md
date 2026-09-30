# `job_profile_prepare`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `job_profile_prepare`

_Préparer une capture Nsight Systems bornée._

**Profils :** `full`, `expert`.

**Effet :** Enregistre un plan local. Peut lire les racines par SSH ; aucune écriture ni soumission sur ROMEO.

## 🎯 Utilisation

Encapsule votre commande dans un script de profilage GPU. La capture commence après delay_seconds et dure duration_seconds pour limiter la taille des traces.

## ⚙️ Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `command` | `str` | Oui | — | Commande de calcul à inscrire dans le script du job. |
| `name` | `str` | Non | `"mcp-profile"` | Nom du job ou de l’opération. |
| `delay_seconds` | `int` | Non | `60` | Délai avant la capture Nsight Systems, en secondes. |
| `duration_seconds` | `int` | Non | `30` | Durée de la capture Nsight Systems, en secondes. |
| `warmup_steps` | `int` | Non | `5` | Valeur PROFILE_WARMUP_STEPS transmise au programme. |
| `profile_steps` | `int` | Non | `10` | Valeur PROFILE_STEPS transmise au programme. |
| `time_limit` | `str` | Non | `"30m"` | Durée maximale, par exemple 1m, 1h ou 2h. |
| `gpus_per_node` | `int` | Non | `1` | Nombre de GPU à réserver par nœud ; 0 pour un calcul sans GPU. |
| `cpus_per_task` | `int` | Non | `16` | Nombre de cœurs réservés par tâche. |
| `arch` | `str` | Non | `"armgpu"` | Architecture cible : x64cpu ou armgpu. null laisse la préparation la déduire lorsque l’outil l’accepte. |
| `spack_packages` | `list[str] \| None` | Non | `null` | Spécifications Spack à charger pour l’architecture du job. |
| `workdir` | `str \| None` | Non | `null` | Répertoire de travail distant autorisé ; null utilise le dossier prévu par la préparation. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## ▶️ Exemple

Arguments JSON à transmettre à `job_profile_prepare` depuis votre client MCP :

```json
{
  "command": "python calcul_gpu.py",
  "arch": "armgpu",
  "gpus_per_node": 1,
  "delay_seconds": 10,
  "duration_seconds": 30
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## 📤 Résultat

Le script de profilage, les chemins de rapport prévus, les ressources et le plan local.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## 📌 Prérequis et limites

delay_seconds est borné de 0 à 3600 et duration_seconds de 5 à 600. warmup_steps et profile_steps sont transmis au programme via des variables ; votre code doit les exploiter pour un profilage par itérations.

## 🔗 Voir aussi

[`plan_get`](plan_get.md) · [`job_profile_submit`](job_profile_submit.md) · [`profile_report`](profile_report.md)

[Code de l’outil](../../romeo_mcp/outils_mesure.py#L516) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)
