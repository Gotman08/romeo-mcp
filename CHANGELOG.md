# Historique des versions

[Accueil](README.md) · [Guide des mises à jour](docs/updates.md)

<details>
<summary>Sommaire de cette page</summary>

- [1.5.0](#150)
- [1.4.0](#140)
- [1.3.0](#130)

</details>

## 1.5.0

Cette version vérifie les mises à jour suivantes : une installation 1.4.0 passe
encore à cette version avec son ancien contrôle SHA-256.

### Espaces projet

- Sous `/project/<code>`, les outils n’écrivent plus que dans le dossier du login SSH, les dossiers de cours et ceux déclarés par `ROMEO_PROJECT_DIRS`. La lecture reste libre.
- Le dossier personnel est créé et refermé en mode `2700` avant chaque écriture. S’il appartient à un autre compte, rien n’est écrit et le refus nomme son propriétaire.
- `login_command_run` applique la règle aux arguments littéraux, y compris après `cd` et dans les redirections, et refuse les suppressions et changements de droits dans ces espaces.

### Chaîne de mise à jour

- Une wheel n’est installée qu’avec une attestation Sigstore valide : provenance SLSA signée par le workflow de release du dépôt, sur le tag de cette version. La vérification tourne dans un venv dédié, épinglé par hash.
- Les dépendances d’une mise à jour viennent d’un verrou livré dans la wheel attestée et s’installent avec `pip --require-hashes --no-deps --only-binary :all:`.
- Les mises à jour se décident hors du modèle : `mcp_update_check` et `mcp_update_status` lisent seulement l’état. L’installation, le retour arrière et l’accord automatique passent par le terminal, et `python -m romeo_mcp update --auto on` exige un terminal interactif. Un accord enregistré sans cette voie n’est pas repris.
- Le workflow de release atteste la wheel, les sources et `SHA256SUMS`.

### RTK et commandes du login

- `rtk_status` vérifie RTK et lit ses statistiques JSON dans les profils `full` et `expert`.
- `login_command_run` propose `use_rtk` et `max_chars`, avec commande demandée, commande exécutée et état de la réécriture. Le mode brut reste le défaut.
- Détection de `~/.local/bin/rtk` même avec un ancien PATH SSH ; délai partagé entre détection, réécriture et exécution. Les refus, erreurs et délais ne déclenchent aucun replay de la commande utilisateur.
- Les garde-fous vérifient aussi les commandes enveloppées par RTK ; les sondes internes et les scripts Slurm préparés conservent leur sortie et leurs commandes exactes.
- [Installation automatique](docs/rtk.md) : au premier besoin, `login_command_run(use_rtk=true)` ou `rtk_status` pose RTK 1.1.0 (édition Apache-2.0, x86_64) dans `~/.local/bin`, sans action de l’utilisateur et jamais au démarrage du serveur. Version, taille et SHA-256 sont épinglés dans le dépôt et toute différence est refusée. Un fichier déjà présent n’est pas remplacé. Un échec laisse la commande en mode brut, figure dans le champ `install` et n’est retenté qu’au démarrage suivant du serveur. `ROMEO_RTK_AUTO_INSTALL=0` désactive cette installation. `rtk_status` n’est donc plus annoncé en lecture seule.

### Intentions et cycles de vie explicites

- Quatorze outils RomeoLLMTool : catalogue, préparation et lancement Slurm sans
  attente, suivi, journaux, accès, gateway, chat ponctuel et diagnostics. Plans
  consommés une fois, fiche revérifiée et arrêt de gateway conservant les jobs.
  Détection de l'installation partagée lorsque la CLI n'est pas dans le PATH SSH.
  [Guide et limites](docs/romeollm.md).
- Cinq outils de rapports GitHub dans tous les profils : accord automatique
  persistant, description filtrée, registre local et liens après reconnexion.
  Création suivie d'une relecture, protection contre les doublons locaux,
  plafonds d'envoi et absence de deuxième POST après résultat incertain.
  Connexion GitHub CLI ou jeton privé ; aucun journal ou argument collecté.
- Erreurs GitHub distinctes d'une absence de mise à jour, cache daté, protection
  contre les doubles installations et distinction version prête/version exécutée.
- Inventaire du test protocole remis à jour et vérifié hors ligne ; remplacement
  atomique de l'état de mise à jour tolérant les lecteurs concurrents Windows.
- Expiration et cloisonnement du cache Spack, cache de statut opt-in avec âge explicite.
- Mesures agrégées du démarrage, des outils et du transport ; guide de choix des outils sans sonde distante.
- Observations Slurm/services persistantes ; distinction soumission, fin ordonnanceur, résultat validé et demande d'annulation.
- Reconnexion réservée aux lectures explicites ; aucune réexécution automatique après envoi SSH ambigu.
- Plans de transfert consommables une seule fois, workers détachés, statuts et journaux relisibles et annulation observée.
- Remplacement atomique tolérant les ouvertures concurrentes Windows et fermeture du registre à la sortie.

- La préparation d'un environnement Python refuse une sélection Spack absente
  ou le nom ambigu `python` avant de créer un plan. Le test réel sur ROMEO a
  montré que ce défaut provoquait un échec Slurm au chargement de Spack.

- Services unifiés : préparation, démarrage sans attente, état, connexion et arrêt.
- Fichiers : création exclusive et remplacement atomique avec empreinte attendue facultative.
- Validation locale séparée de la vérification distante des chemins.
- Relevés de jobs immuables, consultables et exportables sans nouvelle collecte.
- Plans consultables et communs aux installations, roues, téléchargements, profilages, chaînes reprenables et allocations.
- Environnements Python structurés ; exécuteurs génériques limités au catalogue `expert`.
- Migration incompatible des anciens outils composites : voir `docs/Tools.md`.

### Corpus, énergie, rapports et divers

- Corpus ROMEO recollecté le 16 octobre 2026 : 50 pages officielles et
  34 images au lieu de 42 et 21. Ajout de RomeoLLMTool (lancement de LLM par
  Slurm avec vLLM, SGLang ou llama.cpp), du guide de prise en main de l'API
  Oratio et de la page d'authentification au portail ; demande de clé d'API et
  liste des modèles Oratio mises à jour. Le collecteur enregistre les images
  intégrées en `data:`, ne s'interrompt plus sur une console Windows en cp1252,
  place l'ancre après l'extension (`page.md#section`) et ne convertit plus les
  fichiers joints (exemples `.py`, `.md`, `.jpg`) en pages : leurs liens ouvrent
  le site officiel. `verify_corpus` contrôle désormais chaque cible locale,
  quelle que soit son extension.
- Collecte : le collecteur normalise lui-même, sans script de réparation
  externe, les liens dont la cible est restée entre crochets en amont
  (`/documentation/[https://…]`, sept liens de la page d'authentification). Une
  page du site devient un lien local `page.md#ancre`, une URL un lien externe,
  une adresse un `mailto:`. Ces fausses cibles ne sont plus téléchargées : le
  champ `errors` du manifeste ne compte que de vrais échecs, et chaque
  normalisation est consignée dans `link_normalization`. `verify_corpus`
  contrôle aussi les ancres `#fragment` et la casse exacte des noms de fichiers.
- Corpus : `tools/merge_corpus.py` intègre une collecte brute au corpus versionné
  à la place du script annexe. Il ajoute le fil d'Ariane et le pied de page du
  projet, réécrit les ids de titre imposés par le site (`#article1`) en ancres
  calculées, conserve l'en-tête et le pied écrits à la main du sommaire et
  régénère le manifeste. Il compare sans écrire par défaut, ignore les dates de
  collecte, refuse une collecte en erreur ou qui ne passe pas `verify_corpus` et
  ne supprime les fichiers disparus du site qu'avec `--prune`. Une recollecte
  réelle suivie de la fusion redonne le corpus versionné à l'identique, hors
  dates de collecte.
- Énergie et carbone : lecture des compteurs Slurm, attribution uniquement sur
  allocation exclusive vérifiée, données absentes laissées inconnues. Modèle
  facultatif séparé ; suppression du facteur fixe et de l'extrapolation d'une
  puissance instantanée sur toute la durée. Facteur RTE daté, couverture complète
  et périmètre explicite ; les émissions calculées restent une estimation.
- Issues : bot configurable localement sans GitHub CLI, sélection personnelle
  possible, aucun compte ou jeton partagé distribué. Publication limitée au
  diagnostic technique contrôlé, outil, catégorie et versions majeures/mineures ;
  textes libres et empreintes privées exclus. Suppression locale des rapports
  sans effacer la politique ni les quotas de publication.
  Une issue retrouvée dont le titre ou le contenu diffère reste non validée ;
  son lien est conservé pour réconciliation sans nouvelle création.
- Documentation : objets JSON vides expliqués, paramètres manquants complétés,
  liens source et compteurs du catalogue corrigés ; audit des 99 contrats ajouté
  aux vérifications hors ligne.

- Interface terminal interne 0.5 : dossiers liés, reprise avec preuves séparées,
  efficacité demandée/mesurée, groupes Slurm et sessions datées. Favoris et notes
  privés, notifications facultatives sans répétition, présentation anonymisée
  dans les écrans/exports. Filtres combinés et saisie regroupée, recherche sans
  collecte de fichiers, inventaire initial progressif avec compteurs partiels.
  Copie/export en arrière-plan et confirmations visibles malgré les avertissements,
  souris facultative et largeur d'identifiants réglable. Lecture distante uniquement
  par action explicite ; arrêt des helpers détenus lors de la fermeture. Nouvel
  outil local `job_link_artifact`, historique borné des observations, mesures et
  journaux persistés ; dépendances restantes observées et sous-jobs réellement
  enregistrés. Traces anciennes terminées/vérifiées neutres. Compatibilité des
  anciennes préférences et des tableaux 0.4/contrat 2.

- Interface terminal interne 0.4 : recherche et pagination dans tout l'historique,
  jobs actifs prioritaires et compteurs globaux explicites. Alertes ouvrant la
  trace concernée, intégrité des transferts séparée du pourcentage dans la liste.
  Panneau actif défilant, choix liste/détail et largeur réglable ; dates UTC,
  badges et seuils de fraîcheur distincts. Ressources HPC demandées/observées
  séparées, préférences locales, copie et export UTF-8. Index privé en mémoire,
  cache invalidé par fichiers/WAL, transferts modifiés relus individuellement,
  progression d'inventaire et requêtes obsolètes écartées. Mesures reproductibles
  de lecture, rendu, CPU et mémoire ; contrat 3 avec compatibilité du lecteur 2.

- Interface terminal interne 0.3 : recherche française tolérant les accents,
  états et validations harmonisés, transferts à examiner dans l'aperçu, détails
  structurés et panneaux adaptés au contenu. Tris indépendants par date, état
  ou priorité avec sélection conservée, barres de défilement et copie mesurée.
  Modes `--color auto/always/never`, indication du mode monochrome et vérification
  des couleurs réellement produites dans un terminal interactif.

- Interface terminal interne 0.2 : filtres indépendants et visibles, effacement
  en un Échap, pagination, palette sombre et détails complets défilants. Les
  listes restent utilisables dès 48 × 16 et l'aperçu priorise les calculs à examiner.
- Relecture locale explicitement datée, récupération du lecteur avec `r`, délai
  de 10 secondes et conservation du dernier relevé en erreur. Tests de sessions
  PTY avec interruption, blocage, restauration et arrêt des processus détenus.
- Progression mesurée des nouveaux transferts rsync détachés, preuves compactes
  des checkpoints et vue Rapports avec autorisation, occurrences et publication
  enregistrées. Contrat JSON 2 et rendu séparé en modules par vue.

- Première version interne d'un tableau de bord Ratatui facultatif : commande
  `tui`, compilation explicite, démonstration, aperçu, jobs, transferts et mises
  à jour en cache. Lecture seule locale, âges des observations, filtre, pause,
  aide et restauration du terminal ; le serveur MCP stdio reste indépendant.
- Contrat JSON borné, lecteur Python isolé, nettoyage des caractères de contrôle
  et vérification des plans de transfert ; tests Python/Rust et CI Windows/Linux.

- Navigation de la documentation : [accès par besoin depuis le README](README.md#navigation-rapide),
  [index des guides](docs/README.md), sommaires, liens vers les fiches d’outils
  et retours vers les pages parentes. Correction des ancres locales de la
  charte et de la procédure SSH ; sources et dates de collecte conservées.
- Séparation des actions MCP : [`tool_profile_get`](docs/tools/tool_profile_get.md) / [`tool_profile_set`](docs/tools/tool_profile_set.md),
  [`job_log_tail`](docs/tools/job_log_tail.md) / [`job_log_search`](docs/tools/job_log_search.md), préparation et soumission des jobs,
  tableaux et pipelines. Les plans privés conservent les scripts exacts,
  expirent pour soumission après 24 h et empêchent une répétition après
  succès, appel concurrent ou échec partiel.
- [`secret_env_prepare`](docs/tools/secret_env_prepare.md) annonce ses écritures et changements de permissions ;
  [`cluster_gpu_health_run`](docs/tools/cluster_gpu_health_run.md) annonce son allocation GPU. Le faux mode NCCL
  est désactivé. [`storage_usage_audit`](docs/tools/storage_usage_audit.md) remplace le nom suggérant un nettoyage.
- `stage_dataset` n’installe plus implicitement `huggingface_hub` : un venv
  `env_path` préparé explicitement est requis pour les datasets Hugging Face.
- Ces changements retirent les anciens noms du catalogue MCP. Voir le
  [guide de migration](docs/Tools.md#migration-des-anciens-noms).

- Isolation des fichiers de paramètres et des scripts Slurm par soumission,
  avec noms uniques dans le même dossier et empreintes conservées dans la
  provenance. Plusieurs tableaux peuvent partager le même nom et le même
  `workdir` sans remplacer les paramètres encore attendus par leurs tâches (#3).
- `job_output` distingue les octets présents dans stderr des en-têtes et des
  extraits filtrés. Un stderr vide ne masque plus stdout en mode automatique ;
  les journaux sans saut de ligne final restent correctement séparés (#5).

## 1.4.0

### Mises à jour depuis GitHub

- `python -m romeo_mcp update --check` consulte la dernière release stable.
- `python -m romeo_mcp update` présente les notes et demande confirmation.
- Chaque version est préparée dans un environnement Python séparé, avec ses
  dépendances et sa documentation. L’empreinte SHA-256 de la wheel est vérifiée
  avant installation, puis le serveur et les fichiers du corpus sont contrôlés.
- La nouvelle version est sélectionnée au prochain lancement. Les processus
  déjà démarrés poursuivent leurs opérations avec leur environnement actuel.
- `python -m romeo_mcp update --rollback` réactive l’environnement précédent
  après vérification. La configuration personnelle et le registre des jobs
  restent en place.
- Une notification facultative sur la sortie d’erreur signale les nouvelles
  releases au démarrage du serveur, avec une vérification au plus quotidienne.
- Les releases sont publiées après les tests Windows et Linux sur Python 3.11
  et 3.13. Le README principal et sa bannière conservent leur présentation.

Pour les installations antérieures à 1.4.0, effectuer une première mise à jour
manuelle selon le [guide](docs/updates.md#activer-le-système-sur-une-ancienne-installation).

## 1.3.0

- Profils d’outils `essential` et `full`.
- Diagnostic `doctor --live` en lecture seule.
- Fiches de reproductibilité par job et documentation par section.
- Corpus ROMEO embarqué, recherche locale avec pagination et contexte.

---

[↑ Haut de page](#historique-des-versions) · [Accueil](README.md) · [Documentation](docs/README.md) · [Catalogue Tools](docs/Tools.md)
