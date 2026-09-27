# Fiches de reproductibilité

[Accueil](../README.md) › [Documentation](README.md) › Reproductibilité

Une fiche rassemble les informations disponibles pour retrouver les conditions
d’un calcul soumis par ce MCP. Elle distingue les observations faites à des
dates différentes et signale les informations manquantes.

## Choisir les données avant le calcul

Dans `submit_job`, ajoutez les chemins absolus des entrées scientifiques à
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
  "data_files": ["/scratch_p/VOTRE_IDENTIFIANT/experience/entrees.csv"],
  "confirm": false
}
```

Vérifiez la simulation, puis soumettez avec `confirm: true`. Le dossier de
travail peut être un checkout Git : la capture y cherche `HEAD`, sans lancer
de filtre Git, de commande du projet ou de parcours des fichiers non suivis.

Avant la commande du job, le script tente de relever les métadonnées sur le
nœud alloué. Cette étape exige Python 3 et `timeout`, prend au plus 20 secondes
et reste non bloquante en cas d’échec. Elle écrit
`.romeo-provenance/IDENTIFIANT_JOB.json` dans le dossier de travail. Ajoutez
`.romeo-provenance/` au `.gitignore` de vos projets de calcul.

## Exporter après le calcul

Demandez à l’assistant d’appeler :

```json
{
  "job_id": "123456",
  "live": true
}
```

L’outil est `export_job_report`. `job_id` doit appartenir au registre local
du MCP. Une tâche de tableau peut être désignée par `123456_4`, avec le script
conservé pour le tableau parent. Pour un tableau, exportez chaque tâche voulue.

La commande équivalente, avec le Python de votre venv :

```sh
python -m romeo_mcp export-job 123456
python -m romeo_mcp export-job 123456 --offline
```

Options facultatives :

| Option CLI | Argument MCP | Utilité |
|---|---|---|
| `--output-dir DOSSIER` | `output_dir` | Dossier parent local, obligatoirement hors d’un dépôt Git |
| `--code-dir CHEMIN` | `code_dir` | Répertoire Git distant observé lors de l’export ; sinon celui du job |
| `--data-file CHEMIN` (répétable) | `data_files` | Fichiers distants dont relever l’empreinte **au moment de l’export** |
| `--offline` | `live: false` | Produire la fiche à partir du registre local uniquement |

Chaque export crée un nouveau dossier sous `~/.romeo-mcp/reports/` par défaut :

- `report.json` : données structurées, dates, sources et limites.
- `report.md` : présentation lisible des mêmes informations.
- `script.sbatch.txt` : copie filtrée du script conservé à la soumission.

`~` désigne le dossier personnel du compte qui lance le MCP. Les fichiers
existants ne sont jamais écrasés. Sur les systèmes Unix, les dossiers sont
créés en mode `700` et les fichiers en mode `600` ; sur Windows, ils héritent
des autorisations du dossier choisi. L’export lit ROMEO sans soumettre de job.

## Ce qui est réellement mesuré

| Moment | Informations |
|---|---|
| Avant la soumission | Version du MCP, ressources demandées, modules et paquets Spack demandés, référence du conteneur, architecture et commit Git disponible |
| Avant la commande sur le nœud | Commit Git, architecture, version de Python, modules chargés, identifiants Spack chargés et SHA-256 des entrées sélectionnées |
| À l’export | Capture conservée sur le nœud, état et mesures `sacct`, commit et empreintes demandés après coup |

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
