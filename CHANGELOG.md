# Historique des versions

[Accueil](README.md) · [Guide des mises à jour](docs/updates.md)

<details>
<summary>Sommaire de cette page</summary>

- [Non publié — intentions et cycles de vie explicites](#non-publié--intentions-et-cycles-de-vie-explicites)
- [Non publié](#non-publié)
- [1.4.0](#140)
- [1.3.0](#130)

</details>

## Non publié — intentions et cycles de vie explicites

- Cinq outils de rapports GitHub dans tous les profils : accord automatique
  persistant, description filtrée, registre local et liens après reconnexion.
  Création suivie d'une relecture, protection contre les doublons locaux,
  plafonds d'envoi et absence de deuxième POST après résultat incertain.
  Connexion GitHub CLI ou jeton privé ; aucun journal ou argument collecté.
- Mises à jour pilotables par cinq outils MCP dans tous les profils : contrôle
  visible, autorisation automatique persistante, préparation détachée, suivi
  après reconnexion et retour arrière avec écartement de la version annulée.
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


## Non publié

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
