# Historique des versions

[Accueil](README.md) · [Guide des mises à jour](docs/updates.md)

## Non publié — intentions et cycles de vie explicites

- Services unifiés : préparation, démarrage sans attente, état, connexion et arrêt.
- Fichiers : création exclusive et remplacement atomique avec empreinte attendue facultative.
- Validation locale séparée de la vérification distante des chemins.
- Relevés de jobs immuables, consultables et exportables sans nouvelle collecte.
- Plans consultables et communs aux installations, roues, téléchargements, profilages, chaînes reprenables et allocations.
- Environnements Python structurés ; exécuteurs génériques limités au catalogue `expert`.
- Migration incompatible des anciens outils composites : voir `docs/reference.md`.


## Non publié

- Séparation des actions MCP : `tool_profile_get` / `tool_profile_set`,
  `job_log_tail` / `job_log_search`, préparation et soumission des jobs,
  tableaux et pipelines. Les plans privés conservent les scripts exacts,
  expirent pour soumission après 24 h et empêchent une répétition après
  succès, appel concurrent ou échec partiel.
- `secret_env_prepare` annonce ses écritures et changements de permissions ;
  `cluster_gpu_health_run` annonce son allocation GPU. Le faux mode NCCL
  est désactivé. `storage_usage_audit` remplace le nom suggérant un nettoyage.
- `stage_dataset` n’installe plus implicitement `huggingface_hub` : un venv
  `env_path` préparé explicitement est requis pour les datasets Hugging Face.
- Ces changements retirent les anciens noms du catalogue MCP. Voir le
  [guide de migration](docs/reference.md#migration-des-anciens-noms).

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
