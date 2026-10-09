# Rapports GitHub du MCP

[Accueil](../README.md) · [Catalogue](Tools.md#rapports-github-du-mcp)

`mcp_issue_report` permet à l'assistant de signaler un défaut observé de **ROMEO
MCP** dans [Gotman08/romeo-mcp](https://github.com/Gotman08/romeo-mcp/issues).
Les catégories sont `bug`, `performance`, `maintainability` et `documentation`.
Tous les outils de rapport sont présents dans les trois profils.

Un rapport est d'abord filtré et conservé sur votre poste. Par défaut, aucun
envoi GitHub n'a lieu. Après votre accord initial, le modèle peut publier les
rapports pendant sa tâche sans demander une confirmation pour chaque incident.
Le lien de l'issue et l'historique restent consultables. Le serveur ne collecte
pas de journaux en arrière-plan et n'embarque aucun modèle : l'assistant doit
appeler l'outil lorsqu'il constate un défaut.

## Activer une fois

Utilisez la connexion de [GitHub CLI](https://cli.github.com/manual/gh_auth_login) :

```sh
gh auth login --hostname github.com
python -m romeo_mcp issues --enable-automatic --yes
```

Si vous êtes déjà connecté avec `gh`, seul le second appel est nécessaire.
L'autre méthode consiste à fournir `ROMEO_GITHUB_TOKEN` dans l'environnement
privé du serveur. Un jeton finement limité au dépôt doit disposer de
[Issues : write](https://docs.github.com/en/rest/issues/issues#create-an-issue).
Le jeton n'est jamais enregistré dans le registre, les rapports ou les
arguments d'un sous-processus. L'issue est créée au nom du compte GitHub
authentifié, et elle est **publique**.

Un bot déjà créé peut être configuré **localement** avec `ROMEO_GITHUB_BOT_TOKEN`.
`ROMEO_ISSUE_ACCOUNT=bot` l'impose ; `personal` sélectionne la connexion personnelle
et exclut le bot. En mode `auto` (défaut), un jeton personnel prend priorité sur
le bot local, puis le MCP essaie `gh`. Sans authentification, le rapport reste
local. Aucun compte partagé ni jeton n'est fourni avec le logiciel. Le titulaire
crée et protège son compte bot hors du MCP ; le logiciel n'invente pas de compte
et ne demande pas de mot de passe GitHub dans la conversation.

Le modèle dispose du parcours équivalent :

```json
{"automatic": true, "confirm": true}
```

Ces arguments sont ceux de `mcp_issue_policy_set`, après l'accord de
l'utilisateur. `mcp_issue_policy_get` indique la politique effective. La méthode
d'authentification indiquée est configurée, mais elle n'est vérifiée qu'au
moment d'une requête GitHub. Le modèle ne doit pas prétendre être connecté sur
la seule présence de `gh` ou d'une variable.

## Ce que le modèle envoie

Exemple d'arguments pour `mcp_issue_report` :

```json
{
  "tool_name": "job_prepare",
  "category": "bug",
  "summary": "Une option valide manque dans le plan",
  "observed": "Le plan produit ne contient pas l'option demandée.",
  "expected": "Le plan conserve toutes les options validées.",
  "steps": ["Préparer un exemple fictif minimal.", "Relire le plan."],
  "error_code": "PLAN_OPTION_MISSING",
  "diagnostic": "missing_option"
}
```

Cet exemple décrit le format, sans affirmer l'existence de ce défaut.
`tool_name` doit désigner un outil du serveur ; `server` et `terminal` sont
acceptés pour un défaut de démarrage ou de l'interface facultative.

Le rapport local conserve une description filtrée et un contexte. Le filtre
retire les secrets reconnus, valeurs privées configurées, chemins, URLs,
adresses, identifiants de jobs et mentions GitHub. Il ne peut pas reconnaître
tout nom ou toute donnée de recherche inconnue : ne pas les fournir au modèle.

**La publication n'utilise aucun de ces textes libres.** Une projection fermée
construit le titre et le corps à partir du nom public de l'outil, de la catégorie,
d'un diagnostic du catalogue et des versions majeures/mineures. Résumé, observation,
attendu, reproduction, erreur libre, système, architecture, identifiant local et
empreinte du texte privé ne sont pas transmis. Cela s'applique au compte personnel
comme au bot local et aux anciens rapports encore non publiés.

La contrepartie est un diagnostic public plus général. Deux descriptions privées
différentes portant le même diagnostic et les mêmes versions retrouvent la même
issue publique. Pour ajouter une reproduction détaillée, utiliser des données
fictives et la publier volontairement après relecture.

Un arrêt de calcul utilisateur, une erreur de mot de passe ou une ressource
indisponible n'établit pas un défaut du MCP. Les erreurs internes inattendues
incluent un `report_hint` pour aider le modèle à choisir ce parcours, sans
transmettre automatiquement le contenu de l'exception. Les outils `mcp_issue_*`
ne peuvent pas se signaler eux-mêmes et déclencher une boucle de rapports.

## Doublons et résultat vérifié

L'identifiant local porte sur le rapport filtré. L'empreinte publique porte
uniquement sur la projection technique autorisée, sans texte privé. Des appels
identiques retrouvent le même rapport local et incrémentent ses occurrences.

Avant toute création, le serveur lit les issues ouvertes **et fermées**, en
ignorant les PR, pour rechercher l'empreinte. Il ne dépend pas du délai
d'indexation de GitHub Search. Cette lecture est plafonnée à 1 000 entrées et
30 secondes ; si elle reste incomplète, aucun nouvel envoi n'a lieu.
Deux machines distinctes qui publient exactement au même instant peuvent
encore créer deux issues : GitHub ne fournit pas de clé d'idempotence pour
cette opération. Le verrou local protège les processus qui partagent le registre.

Une issue retrouvée doit également conserver le titre et le corps techniques
attendus. Si son contenu diffère, son lien est conservé pour vérification manuelle :
`result_validated=false`, sans création d'un nouvel exemplaire après reconnexion.

Après la création, le serveur relit l'issue par son numéro et vérifie son
contenu. `result_validated=true` correspond à une observation réussie, datée
par `status.updated_at`, pas à un simple envoi. Les consultations locales
suivantes restituent cette preuve historique, sans nouvelle requête GitHub.

| État | Signification |
|---|---|
| `local_only` | Rapport conservé ; aucun envoi confirmé |
| `publishing` | Intention d'envoi conservée ; opération en cours ou interrompue |
| `published` | Création suivie d'une relecture vérifiée |
| `duplicate` | Issue portant déjà cette empreinte retrouvée sur GitHub |
| `failed` | Refus connu ou erreur avant une création potentielle |
| `publication_unknown` | GitHub a peut-être créé l'issue ; succès non établi |
| `rate_limited` | Rapport conservé jusqu'à `retry_after` |

Après une coupure, `mcp_issue_publish` peut retrouver l'issue par son numéro ou
son empreinte. Si un envoi précédent reste incertain et que l'issue n'est pas
retrouvée, il ne fait **aucun deuxième POST**, même avec `confirm=true`.
Il faut vérifier GitHub manuellement. Une confirmation n'est pas un moyen de
contourner cette protection.

Un ancien envoi incertain créé avant la projection publique fermée reste à
vérifier manuellement : le MCP ne transmet pas son ancienne empreinte privée
et ne recrée pas une nouvelle issue à sa place.

## Consulter ou arrêter

```sh
python -m romeo_mcp issues
python -m romeo_mcp issues --report-id IDENTIFIANT_DU_RAPPORT
python -m romeo_mcp issues --disable-automatic
python -m romeo_mcp issues --delete-local --report-id IDENTIFIANT_DU_RAPPORT --yes
```

`mcp_issue_status` fournit le même historique local : vingt rapports récents ou
un rapport précis. La désactivation arrête les nouveaux envois automatiques ;
elle ne supprime pas les issues déjà publiées. Pour publier un seul rapport
sans activer l'automatisme, utilisez `mcp_issue_publish(report_id=..., confirm=true)`
après l'accord ponctuel de l'utilisateur.

Le registre SQLite est placé dans `issue-reports/`, à côté de `ROMEO_CONFIG`,
donc hors du dépôt par défaut. `ROMEO_REPORTS_DIR` peut choisir une autre racine
hors Git. La politique est partagée par les processus utilisant ce registre.
`ROMEO_AUTO_ISSUES=0` force la désactivation automatique ; `1` exprime un accord
de configuration. Ces surcharges ont priorité sur la politique enregistrée.

Les créations sont limitées à cinq tentatives par période glissante de
24 heures, avec au moins 60 secondes d'écart. Les limites GitHub et les erreurs
imposent aussi un délai, conservé après reconnexion. Le registre accepte
1 000 rapports ; archivez-le avec le serveur arrêté avant d'en créer davantage.
Les rapports préexistants ne sont pas envoyés en masse lors de l'activation.
Les signalements alimentent la maintenance ; ils n'appliquent aucune correction
et ne déclenchent pas de fusion de code.

## Confidentialité et suppression

Les envois restent désactivés par défaut et peuvent être retirés. La politique
expose `publication_privacy` pour rendre les champs transmis explicites.
Le **pseudo GitHub de l'auteur reste public** ; utiliser son compte personnel
n'est pas une publication anonyme. GitHub reçoit aussi les métadonnées nécessaires
à la connexion HTTPS. Le MCP ne collecte pas d'identifiant de poste ou de suivi.

`--delete-local --yes` efface tous les contenus locaux ; avec `--report-id`, seul
ce rapport est effacé. Les quotas de tentatives et la politique sont conservés
séparément pour éviter de contourner les protections anti-spam. Cette suppression
locale ne supprime ni les issues publiques ni leurs copies éventuelles. Définir
une durée de conservation adaptée au contexte et supprimer les descriptions
locales qui ne sont plus nécessaires. Les copies et sauvegardes du registre
doivent également être traitées.

Ces protections techniques appliquent la minimisation ; elles ne constituent
pas une certification juridique RGPD et ne garantissent pas l'anonymat du compte
GitHub. Le responsable du déploiement doit informer les personnes, définir les
finalités et traiter les demandes relatives aux publications publiques.
Sources : [minimisation CNIL](https://www.cnil.fr/fr/minimiser-les-donnees-collectees),
[guide RGPD du développeur](https://www.cnil.fr/fr/guide-rgpd-du-developpeur).
