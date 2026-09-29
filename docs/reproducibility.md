# Fiches de reproductibilité

[Accueil](../README.md) › [Documentation](README.md) › Reproductibilité

Une fiche rassemble les informations disponibles pour retrouver les conditions
d’un calcul soumis par ce MCP. Elle distingue les observations faites à des
dates différentes et signale les informations manquantes.

## Choisir les données avant le calcul

Dans `job_prepare`, ajoutez les chemins absolus des entrées scientifiques à
`data_files`. Exemple à adapter avec votre propre répertoire scratch :

```json
{
  "name": "experience",
  "command": "python analyse.py",
  "arch": "x64cpu",
  "time_limit": "5m",
  "cpus_per_task": 1,
  "mem_gb": 2,
  "workdir": "/scratch_p/VOTRE_IDENTIFIANT/experience",
  "data_files": ["/scratch_p/VOTRE_IDENTIFIANT/experience/entrees.csv"]
}
```

Vérifiez le plan, puis appelez `job_submit` avec son `plan_id` et `confirm: true`. Le dossier de
travail peut être un checkout Git : la capture y cherche `HEAD`, sans lancer
de filtre Git, de commande du projet ou de parcours des fichiers non suivis.

Avant la commande du job, le script tente de relever les métadonnées sur le
nœud alloué. Cette étape exige Python 3 et `timeout`, prend au plus 20 secondes
et reste non bloquante en cas d’échec. Elle écrit
`.romeo-provenance/IDENTIFIANT_JOB.json` dans le dossier de travail. Ajoutez
`.romeo-provenance/` au `.gitignore` de vos projets de calcul.

## Collecter puis exporter après le calcul

1. Appeler `job_report_collect(job_id="123456", data_files=[...])`. La collecte
   lit ROMEO et enregistre un relevé immuable dans le registre local ; elle
   rend `report_id`, `created_at` et `report_sha256`.
2. Relire ce relevé avec `job_report_get(report_id)` si nécessaire.
3. Appeler `job_report_export(report_id, output_dir=...)`. L'export écrit
   uniquement les fichiers locaux, sans SSH ni nouvelles empreintes.

Deux exports du même relevé ont le même contenu et le même horodatage de
collecte. Pour obtenir des mesures plus récentes, effectuer une nouvelle
collecte, qui reçoit un nouvel identifiant. Les informations indisponibles
sont conservées comme manquantes dans le relevé.

`job_report_from_record(job_id)` crée un relevé depuis le registre local,
sans SSH. Il s'exporte ensuite de la même façon. Un `job_id` doit être connu
du registre ; une tâche de tableau peut être désignée par `123456_4`.

La CLI conserve un raccourci qui compose explicitement collecte et export :

```sh
python -m romeo_mcp export-job 123456
python -m romeo_mcp export-job 123456 --offline
```

| Option CLI | Outil MCP correspondant | Utilité |
|---|---|---|
| `--output-dir DOSSIER` | `job_report_export(..., output_dir=...)` | Destination locale hors de Git |
| `--code-dir CHEMIN` | `job_report_collect(..., code_dir=...)` | Répertoire Git observé lors de la collecte |
| `--data-file CHEMIN` | `job_report_collect(..., data_files=[...])` | Empreintes au moment de la collecte |
| `--offline` | `job_report_from_record(job_id)` | Relevé depuis le registre local |

Chaque export crée un nouveau dossier sous `~/.romeo-mcp/reports/` par défaut :

- `report.json` : données structurées, dates, sources et limites.
- `report.md` : présentation lisible des mêmes informations.
- `script.sbatch.txt` : copie filtrée du script conservé à la soumission.

`~` désigne le dossier personnel du compte qui lance le MCP. Les fichiers
existants ne sont jamais écrasés. Sur les systèmes Unix, les dossiers sont
créés en mode `700` et les fichiers en mode `600` ; sur Windows, ils héritent
des autorisations du dossier choisi. La collecte lit ROMEO sans soumettre de job ; l’export ne contacte pas ROMEO.

## Ce qui est réellement mesuré

| Moment | Informations |
|---|---|
| Avant la soumission | Version du MCP, ressources demandées, modules et paquets Spack demandés, référence du conteneur, architecture et commit Git disponible |
| Avant la commande sur le nœud | Commit Git, architecture, version de Python, modules chargés, identifiants Spack chargés et SHA-256 des entrées sélectionnées |
| À la collecte | Capture conservée sur le nœud, état et mesures `sacct`, commit et empreintes demandés après coup |

Les ressources Slurm comprennent l’allocation, le temps écoulé, le temps CPU,
la mémoire maximale lorsqu’elle est disponible et les codes de sortie.
Les lignes du job et de ses étapes restent séparées : `MaxRSS` est souvent
fourni sur l’étape `.batch`. Les champs absents restent absents ou vides ; une
absence de mesure n’est pas assimilée à une consommation nulle. Les identifiants
de tableaux suivent le format décrit par [Slurm](https://slurm.schedmd.com/sacct.html).

Un job en attente peut déjà être exporté. Sa capture et ses mesures finales
seront alors manquantes. Les anciens jobs sans provenance enregistrée restent
exportables avec leur script et les informations encore disponibles. Le mode
hors ligne ne récupère pas une capture distante.

Les nouvelles soumissions conservent aussi `submission.artifacts` : chemin et
SHA-256 du script généré, ainsi que ceux du fichier de paramètres pour les
tableaux. Ces empreintes portent sur le contenu envoyé par le MCP avant la
soumission (`source: generated_content`), et non sur une observation distante
après le calcul. Le contenu des paramètres n'est pas ajouté à cette métadonnée.

## Périmètre et protection des données

- Chaque relevé traite au plus **20 fichiers**, **64 Mio au total**, sans
  parcours récursif. Un fichier trop grand, inaccessible ou modifié pendant
  sa lecture reçoit un état explicite. Les fichiers de secrets reconnaissables
  par leur chemin sont refusés, y compris après résolution des liens symboliques.
- Seuls les chemins, tailles et empreintes des données sont conservés, jamais
  leur contenu. Pour de gros jeux de données, sélectionnez un manifeste existant
  qui décrit les entrées et leurs empreintes, en conservant aussi ce manifeste.
- Le relevé conserve le premier démarrage d’un job, sans écraser sa capture lors
  d’une remise en file. Il ne décrit pas automatiquement chaque tentative.
- Le commit ne prouve pas que le checkout était propre. Une commande qui active
  ensuite un venv ou un conteneur peut utiliser un autre environnement. Le MCP
  ne lance ni `pip freeze`, ni inventaire complet des variables, ni lecture des
  URL Git ou du contenu des conteneurs.
- Avant écriture, le filtre masque les clés privées, jetons reconnaissables,
  affectations sensibles, URL authentifiées et corps de heredocs. Le script
  filtré peut donc nécessiter une adaptation avant réexécution ; son SHA-256
  correspond aux octets exportés.
- Les chemins de calcul et les références de projet peuvent rester dans la
  fiche. Les valeurs opaques sans marqueur exigent une revue avant partage.
  Le refus d’exporter dans Git protège le dépôt contre l’ajout accidentel de
  ces rapports personnels.

Le registre local existant reste privé et conserve les scripts d’origine.
L’export n’altère ni ce registre ni le script exécuté sur ROMEO.
