# `romeo_selfcheck`

[Accueil](../../README.md) › [Documentation](../README.md) › [Tools](../Tools.md) › `romeo_selfcheck`

_Comparer le modèle du MCP au cluster actuel._

**Profils :** `full`, `expert`.

**Effet :** Lecture distante par SSH, sans soumission de nouveau job ni modification de fichiers.

**Dans cette fiche :** [Utilisation](#utilisation) · [Paramètres](#paramètres) · [Exemple](#exemple) · [Résultat](#résultat) · [Prérequis et limites](#prérequis-et-limites) · [Voir aussi](#voir-aussi)

## Utilisation

Confronte les limites et capacités encodées dans le serveur aux observations Slurm : partitions, nœuds, architectures, capacités, limites du compte et outils annoncés absents.

## Paramètres

Cet outil ne prend aucun paramètre. Utiliser un objet vide `{}`.

## Exemple

Arguments JSON à transmettre à `romeo_selfcheck` depuis votre client MCP :

```json
{}
```

Cet appel ne contient aucun identifiant ni valeur à remplacer.

## Résultat

Un relevé des écarts entre les hypothèses du serveur et les données observées.

Vérifier `ok` dans la réponse ; en cas d’échec, lire `error` avant de poursuivre.

## Prérequis et limites

L’outil signale les écarts sans corriger le modèle. Il est utile après une maintenance ou lorsqu’une validation de ressources paraît incohérente.

## Voir aussi

[`romeo_status`](romeo_status.md) · [`romeo_software`](romeo_software.md)

[Code de l’outil](../../romeo_mcp/outils_contexte.py#L645) · [Configuration](../configuration.md) · [Retour au catalogue Tools](../Tools.md)

---

[↑ Haut de page](#romeo_selfcheck) · [Cluster et ordonnancement](../Tools.md#cluster-et-ordonnancement) · [Accueil](../../README.md) · [Documentation](../README.md) · [Catalogue Tools](../Tools.md)

Cet outil ne prend aucun argument : `{}` est l’objet JSON attendu.
