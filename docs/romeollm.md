# Utiliser RomeoLLMTool avec le MCP

[Accueil](../README.md) › [Documentation](README.md) › RomeoLLMTool

Les outils `romeollm_*` permettent de choisir une fiche, lancer un modèle sur
Slurm, suivre son démarrage et l'appeler par la gateway officielle. La CLI
RomeoLLMTool gère ses propres moteurs, fiches et jobs ; aucun moteur n'est
installé ou exécuté sur le nœud de connexion par le MCP.

## Lancer un modèle

1. Appeler [`romeollm_catalog`](tools/romeollm_catalog.md) avec `{}` pour trouver
   les fiches disponibles. Passer `fiche` pour consulter un détail, ou `category`
   pour filtrer la liste. Les noms disponibles sont ceux de votre catalogue.
2. Appeler [`romeollm_launch_prepare`](tools/romeollm_launch_prepare.md) avec la
   fiche choisie et une durée. Le projet configuré est utilisé si `project_code`
   est omis. La préparation lit la fiche et son `--dry-run`, sans soumettre.
3. Relire la commande et l'aperçu. Le plan reste consultable par
   [`plan_get`](tools/plan_get.md) pendant 24 heures.
4. Appeler [`romeollm_launch`](tools/romeollm_launch.md) avec le `plan_id` reçu
   et `confirm: true`. La fiche est vérifiée à nouveau et la CLI utilise
   `--no-wait` : le retour n'attend pas que le modèle soit chargé.
5. Consulter [`romeollm_status`](tools/romeollm_status.md), puis
   [`romeollm_logs`](tools/romeollm_logs.md) et
   [`romeollm_endpoint`](tools/romeollm_endpoint.md) avec le numéro Slurm observé.

Exemple de préparation, avec un nom de fiche fictif à remplacer :

```json
{
  "fiche": "exemple",
  "time_limit": "1h"
}
```

La durée est comprise entre une minute et 24 heures. Une réservation Slurm
peut être passée par `reservation`. Le MCP fige la commande et l'empreinte de
la fiche, puis la CLI régénère son script au lancement ; les fichiers distants
ne sont pas verrouillés entre ces deux étapes. Les aperçus filtrent les secrets.

Un même plan ne relance jamais un deuxième job. Après une coupure SSH, son
résultat peut rester inconnu : consulter l'état avant de préparer un autre
lancement. Préparer deux plans distincts reste une demande de deux jobs.

## Accéder au modèle et envoyer un message

[`romeollm_gateway_start`](tools/romeollm_gateway_start.md) démarre la gateway
avec `confirm: true`, pour huit heures par défaut. Le port est choisi par la CLI
si omis. [`romeollm_gateway_status`](tools/romeollm_gateway_status.md) lit son
URL et propose une commande SSH et une URL locale à partir de l'adresse
observée ; aucun tunnel n'est ouvert automatiquement.

Les réponses ne récupèrent pas la clé de gateway et n'utilisent jamais
`endpoint --show-key`. Pour configurer un client personnel, exécuter soi-même
la commande `api_key_command` sur ROMEO et conserver la clé dans son
environnement privé. Les sorties des commandes sont filtrées avant leur retour.
La clé de gateway s'applique à la gateway uniquement ; un accès direct à un job
utilise sa propre clé interne. Les tunnels proposés ne certifient pas l'authentification.

[`romeollm_chat`](tools/romeollm_chat.md) envoie ensuite un message au modèle
déjà disponible dans la gateway, sans boucle interactive ni streaming :

```json
{
  "model": "example/model",
  "message": "Bonjour",
  "max_tokens": 512,
  "timeout_seconds": 60
}
```

Le message est transmis à ROMEO. Le délai borne l'attente du MCP ; une coupure
ne prouve pas que le serveur a annulé la requête. Le nom du modèle doit
correspondre à celui exposé par la gateway.

## Arrêter et diagnostiquer

[`romeollm_stop`](tools/romeollm_stop.md) exige un numéro de job précis et
`confirm: true`. Aucun arrêt global ni nom de fiche ambigu n'est accepté.
[`romeollm_gateway_stop`](tools/romeollm_gateway_stop.md) utilise toujours
`--keep-jobs` : arrêter la gateway conserve les modèles et leur allocation.
Vérifier l'état après chaque demande d'arrêt.

Le profil `full` ajoute [`romeollm_engines`](tools/romeollm_engines.md),
[`romeollm_doctor`](tools/romeollm_doctor.md) sans correction automatique, et
[`romeollm_stats`](tools/romeollm_stats.md). Les onze outils du parcours
courant sont également annoncés dans `essential`.
[`romeo_capabilities`](tools/romeo_capabilities.md) avec `task: "llm"` retrouve
les quatorze outils et indique leur visibilité dans le profil courant.

## Installation distante et vérifications

RomeoLLMTool doit déjà être accessible au compte et au nœud de connexion
utilisés par SSH. L'accès et l'état de préproduction sont décrits dans la
[présentation officielle embarquée](../romeo_mcp/documentation/services/RomeoLLMtool.md).
Si le binaire est hors du PATH, la variable d'environnement du serveur
`ROMEO_LLM_EXECUTABLE` accepte son chemin distant. Il s'agit d'un exécutable
unique, sans fragment shell. Aucun paquet n'est installé automatiquement.

Les outils rendent `output` au format texte de la CLI, ainsi que `exit_code`,
`complete`, `truncated` et une date d'observation. Un succès de commande ne
certifie pas que le modèle est prêt. Aucun argument `--json` non documenté
n'est supposé.

La suite `python tests/run_all.py --only romeollm` utilise une CLI fictive,
un vrai registre local et un client MCP stdio. Elle ne réserve aucune ressource
ROMEO. Un test d'inférence réel doit être autorisé explicitement.

[Catalogue des outils](Tools.md#romeollmtool) · [CLI officielle](../romeo_mcp/documentation/services/RomeoLLMtool/cli.md) · [Tests](../tests/README.md)
