# `job_status`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `job_status`

_Lire l’état d’un job Slurm._

**Profils :** `essential`, `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Interroge la file squeue puis, pour un job terminé, l’historique sacct. Aide à distinguer un calcul en attente, en cours, terminé ou en échec.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `job_id` | `str` | Oui | — | Identifiant du job Slurm à consulter ou à modifier. |

Les paramètres facultatifs peuvent être omis. `null` n’est accepté que pour les types indiquant `None`.

## Exemple

Arguments JSON à transmettre à `job_status` depuis votre client MCP :

```json
{
  "job_id": "123456"
}
```

Les identifiants, chemins et valeurs en majuscules sont illustratifs : utiliser ceux de votre configuration et des réponses précédentes.

## Résultat

L’état et les informations disponibles dans Slurm, avec un démarrage estimé lorsqu’il est fourni pour un job en attente.

La lecture conserve une observation datée et les sous-jobs numériques réellement
retournés par Slurm. `dependencies_remaining` contient les dépendances restantes
du relevé squeue (`%E`), une chaîne vide si Slurm indique leur absence, ou `null`
si cette information n'a pas été fournie. Aucune interrogation supplémentaire
n'est nécessaire. Un état global de tableau inconnu ne supprime pas les preuves
de ses sous-jobs observés.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

L’estimation de démarrage peut être absente ou changer. COMPLETED indique la fin du processus ; la validité des résultats scientifiques reste à vérifier.

## Voir aussi

[`job_log_tail`](job_log_tail.md) · [`job_efficiency`](job_efficiency.md) · [`diagnose_job`](diagnose_job.md)

[Code de l’outil](../../romeo_mcp/outils_calcul.py#L184) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#job_status) · [Préparation et gestion des jobs](../Tools.md#préparation-et-gestion-des-jobs) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)
