# Concurrence entre clients et outils ROMEO MCP

Les opérations sur des ressources indépendantes peuvent progresser en parallèle.
Une opération concurrente incompatible est refusée avant sa copie ou son écriture ;
elle n'est pas mise en attente puis rejouée automatiquement. Relire le résultat
du propriétaire et, pour une modification de texte, l'empreinte du fichier avant
une nouvelle tentative.

Les lectures de contexte ne prennent pas la réservation exclusive d'un écrivain.
`read_remote_file` peut observer l'ancien ou le nouveau contenu publié atomiquement.
`list_dir` est un instantané évolutif : une entrée disparue entre l'énumération et
sa lecture est ignorée et comptée dans `disappeared_entries`. Les autres erreurs
(répertoire absent, permissions, confinement) restent des erreurs. La borne
`limit` et le drapeau `truncated` portent sur les noms sélectionnés initialement ;
une entrée disparue n'est pas remplacée par un autre nom.

## Réservations de fichiers

`file_create`, `file_replace`, les transferts synchrones et leurs workers utilisent
la même réservation sur ROMEO. Un téléchargement réserve sa source en lecture ;
un téléversement réserve sa destination en écriture. Plusieurs lectures coexistent.
Un écrivain exclut les lecteurs et les autres écrivains. Une réservation de
répertoire couvre ses descendants. Les chemins physiques, les alias GPFS et les
liens durs existants sont rapprochés ; deux fichiers frères restent indépendants.

La source locale d'un téléversement est réservée en lecture. La destination locale
d'un téléchargement est réservée en écriture entre les processus qui partagent
le cache de concurrence. Le téléchargement copie dans un dossier privé situé
à côté de la destination, vérifie l'empreinte disponible et publie ensuite le
fichier avec `os.replace`. Une copie échouée ou annulée avant publication conserve
la destination existante. Une modification extérieure de l'identité, taille ou
date du fichier de destination fait également refuser la publication.

La fusion dans un répertoire existant publie les fichiers individuellement :
elle ne constitue pas une transaction atomique sur l'arbre entier. Une erreur
pendant cette fusion peut laisser certains fichiers déjà publiés.

Les réservations sont indexées par SQLite ; le verrou du registre ne couvre
que leur acquisition et libération. Chaque propriétaire conserve un verrou
du noyau sur un fichier témoin. La mort du processus libère ce verrou et la
prochaine acquisition récupère la réservation périmée, sans délai ni recyclage
d'identifiant de processus. Les indices et fichiers témoins résident dans
`~/.romeo-mcp/concurrency` ; localement `ROMEO_CONCURRENCY_ROOT` permet de choisir
un autre cache partagé. Sur ROMEO, les helpers utilisent le cache du home découvert.
Ces métadonnées persistantes font partie du fonctionnement normal du serveur.
Ne pas supprimer ce cache pendant une opération active.

## Couverture du catalogue

| Famille | Coordination et comportement |
|---|---|
| `file_create`, `file_replace` | Réservation d'écriture commune aux transferts ; publication atomique. Création sans écrasement ; remplacement avec contrôle d'empreinte facultatif. |
| `upload_to_romeo`, `download_from_romeo` | Réservations locales et distantes ; publication du fichier après la copie et le contrôle d'intégrité. Les répertoires ont une réservation hiérarchique. |
| `transfer_prepare`, `transfer_start`, `transfer_status`, `transfer_cancel` | Plans uniques, démarrage à usage unique et propriétaire exclusif du worker. Les transferts différents utilisent aussi les réservations de fichiers. Annulation explicite observée séparément de sa demande. |
| Configuration locale, dont `configure` | Réservation avant lecture, fusion et écriture du JSON ; une mise à jour concurrente incompatible échoue sans perdre silencieusement un champ déjà enregistré. |
| Tous les outils `*_submit`, services, environnements Python, téléchargements via job | Réservation de l'intention exacte, puis transaction du registre des plans. Deux identifiants de plan pour les mêmes scripts et la même cible ne peuvent pas soumettre simultanément. Une intention active ou incertaine reste bloquée. |
| Protection et rétention de checkpoints | Réservation commune du calcul source et de sa sauvegarde, même si deux copies visent des sauvegardes différentes ; verrou du noyau récupérable après arrêt. |
| `tool_profile_set` | Un seul changement en cours par connexion, jusqu'à la notification et la capture de sa réponse. Les profils restent propres à chaque processus stdio. |
| Mises à jour et retours | Verrous du noyau existants sur le contrôle et la transaction de l'installation ; workers distincts des serveurs actifs. |
| Rapports et publication d'issues | Identifiants immuables, création exclusive, transactions SQLite et verrou de publication existants. Un envoi incertain ne provoque pas un second POST automatique. |
| Lectures, diagnostics, documentation et préparation | Pas de verrou global sur les fichiers utilisateurs. Le protocole à sentinelles de chaque session SSH reste sérialisé ; les écritures texte utilisent la session longue et les lectures la session courte. Les copies SCP ont leur propre connexion. Les caches et métriques conservent leurs verrous internes. |
| Exécuteurs de shell experts et programmes de calcul | Leur contenu arbitraire ne permet pas d'inférer toutes les ressources modifiées. Ils doivent respecter les mêmes réservations s'ils interviennent sur des fichiers utilisés par un transfert ou une écriture MCP. |

## Soumissions et interruptions

Le registre local conserve l'intention soumise au-delà de la fin de l'appel.
Une réponse de `sbatch` perdue, invalide ou sans identifiant ne prouve pas que
la soumission a échoué : le plan devient `uncertain`, avec `retry_safe=false`.
Un autre plan pour la même intention est refusé. Un refus explicite de
l'ordonnanceur sans étape acceptée permet de préparer une nouvelle tentative.
Un job connu doit avoir un état terminal enregistré avant de réutiliser son
intention. Les clients doivent partager le même registre local pour cette
protection persistante ; deux postes avec des registres séparés ne disposent
pas d'une garantie globale de déduplication des soumissions.

Une annulation du RPC MCP ne tue pas nécessairement l'opération synchrone déjà
en cours. Elle continue d'occuper sa capacité jusqu'à la fin réelle du worker.
Pour interrompre une copie supervisée, utiliser `transfer_cancel` puis observer
`transfer_status`. Un arrêt forcé peut conserver un staging privé incomplet ;
la récupération du verrou ne constitue pas une preuve de nettoyage de ce staging.

## Bornes et limites

- 64 appels MCP admis simultanément par processus : au plus 48 mutations et
  16 lectures, incluant ceux qui attendent un worker. Les suivants reçoivent `busy=true` et
  `execution_started=false` sans exécuter le corps de l'outil.
- Les annotations `readOnlyHint=true` enregistrées par le serveur déterminent
  les lectures. Un outil sans cette annotation, ou inconnu, compte comme mutation.
  La capacité réservée aux lectures reste disponible à saturation des mutations.
  Une saturation des 16 lectures peut encore faire refuser une autre lecture.
- 128 réservations simultanées par cache et 64 ressources au maximum par
  réservation. L'index SQLite attend au plus trois secondes son verrou.
- Les outils synchrones utilisent deux limiteurs AnyIO distincts : 32 workers
  pour les mutations et 16 pour les lectures. Ils ne consomment pas le limiteur
  par défaut du SDK, également utilisé par les entrées et sorties stdio.
  `tools/list` reste donc disponible pendant les opérations bloquées. Les outils
  asynchrones restent natifs, avec les mêmes bornes d'admission et de validation.
  Les workers conservent le contexte et la conversion de sortie du SDK.
- Des lectures distantes d'une même session SSH restent sérialisées par son
  protocole ; plusieurs clients ont des sessions indépendantes. La séparation
  des workers ne promet pas un instantané transactionnel des fichiers.
- Les protections de fichiers sont coopératives : tous les clients doivent
  exécuter cette version et partager le cache concerné. Un éditeur, un shell,
  un ancien MCP ou un job qui écrit directement n'est pas automatiquement bloqué.
- `expected_sha256` est nécessaire pour refuser une modification fondée sur
  une lecture devenue ancienne. Le verrou protège le chevauchement d'opérations ;
  un remplacement sans empreinte reste un remplacement volontaire du contenu courant.
- Une intention désigne les scripts exacts, pas l'ensemble des calculs susceptibles
  d'écrire au même endroit. Deux scripts différents restent deux intentions distinctes.

## Vérification

`python tests/run_all.py --only concurrency` exerce les collisions entre threads
et processus, les alias, les répertoires, la mort d'un propriétaire, les échecs
de copie, les limites et l'annulation réelle d'un RPC stdio. Sur POSIX, la suite
exécute aussi les helpers distants pour vérifier les conflits entre outils.
`context-concurrency` vérifie la capacité réservée, le maintien du contexte et
des schémas, les refus avant exécution, l'annulation et les lectures sous charge
à travers le véritable transport stdio, avec les effets distants simulés.
`tool-actions` vérifie les soumissions concurrentes avec Slurm simulé.
La suite complète par défaut reste hors ligne ; ne pas utiliser `--live` pour
une campagne où les jobs sont interdits.

Une mise à jour des sources ne remplace pas les modules déjà importés. Reconnecter
tous les clients MCP après installation pour activer ces protections ensemble.
Les anciens plans prêts contenant les helpers de checkpoints ou MPI doivent
être préparés à nouveau pour inclure le module de réservation scellé.
