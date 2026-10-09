# `job_link_artifact`

[Documentation](../README.md) · [Catalogue](../Tools.md) · [Tableau terminal](../terminal.md)

Associe explicitement un artefact existant au dossier local d'un job enregistré.
Disponible dans les profils `full` et `expert`. L'outil vérifie l'existence de
chaque objet avant de sauvegarder l'association ; un second appel identique ne
crée pas de doublon.

| Paramètre | Valeurs |
|---|---|
| `job_id` | Identifiant d'un job présent dans le registre local |
| `kind` | `transfer`, `report`, `result` ou `job` |
| `artifact_id` | Identifiant existant renvoyé par le MCP |

```json
{
  "job_id": "123456",
  "kind": "transfer",
  "artifact_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}
```

Les identifiants sont illustratifs. `report` désigne un rapport GitHub du MCP
conservé localement ; `result` désigne un relevé collecté par `job_report_collect`.
La réponse conserve `result_validated: false` : l'association ne démontre ni
l'intégrité de l'artefact ni la validité scientifique du calcul.

L'effet est une écriture SQLite locale. Aucun SSH, transfert, soumission,
publication GitHub ou changement d'état technique n'est exécuté.

[Code de l’outil](../../romeo_mcp/outils_calcul.py#L463)
