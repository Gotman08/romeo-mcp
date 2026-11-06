# `rtk_status`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `rtk_status`

_Vérifier RTK et ses statistiques sur le login._

**Profils :** `full`, `expert`.

**Effet :** Lecture de la disponibilité, de la version et des statistiques. Si RTK manque, installation unique de la release épinglée dans `~/.local/bin` ; aucun fichier remplacé, aucune modification de configuration ni soumission de job.

## Utilisation

Détecte le lanceur `~/.local/bin/rtk` ou un binaire dans le PATH. S’il n’y a ni l’un ni l’autre, le MCP installe RTK dans le home, sans action de votre part : voir [RTK sur le login](../rtk.md), qui explique aussi comment désactiver cette installation. Le contrôle est limité au login : il ne certifie pas la compatibilité du binaire sur un nœud ARM. Un lanceur adapté peut choisir le binaire de chaque architecture.

## Paramètres

| Paramètre | Type | Obligatoire | Défaut | Explication |
|---|---|---|---|---|
| `include_gain` | `bool` | Non | `true` | Inclure les statistiques JSON de `rtk gain`, avec une limite de capture de 16000 caractères. |

Tous les paramètres sont facultatifs. L’objet vide demande la version et les statistiques.

## Exemple

```json
{}
```

```json
{"include_gain": false}
```

## Résultat

`available`, `path` et `version` décrivent l’installation observée. `pinned_version` indique la version que le MCP installerait. `install` n’apparaît que si RTK manquait au moment de l’appel et [rend compte de l’installation](../rtk.md#lire-le-résultat). `gain` contient les statistiques JSON lorsque demandées. `ok=true, available=false` signifie que RTK reste absent : `install` en donne la raison. Une version invalide, une erreur ou des statistiques tronquées ne sont pas présentées comme une mesure complète.

## Prérequis et limites

La détection, la version et les statistiques partagent un délai de 15 secondes ; une installation a son propre délai de 45 secondes au plus. La télémétrie est désactivée pour ces appels, sans changer la configuration sauvegardée. Les statistiques de RTK sont des estimations sur les sorties de commandes, pas une mesure de facturation du modèle.

Le MCP ne passe pas par les hooks Claude Code/Codex : demander `login_command_run(use_rtk=true)` dans le profil `expert`. Les sondes internes qui décodent des données structurées conservent leur sortie exacte. Sur un nœud de calcul, inscrire explicitement le chemin du lanceur RTK dans le plan ; aucune réécriture distante n’est introduite après sa relecture.

## Voir aussi

[RTK sur le login](../rtk.md) · [`login_command_run`](login_command_run.md) · [`compute_command_prepare`](compute_command_prepare.md) · [`tool_profile_set`](tool_profile_set.md)

[Code de l’outil](../../romeo_mcp/outils_execution.py#L202) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)
