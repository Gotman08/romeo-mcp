# Contribuer

Les corrections de documentation, exemples scientifiques et améliorations
des diagnostics sont bienvenues. Une issue utile indique le comportement
attendu, les versions et une reproduction courte avec des données fictives.

## Installation de développement

Depuis la racine du dépôt, avec le Python du venv :

```sh
python -m pip install -e ".[docs]" build
python tests/run_all.py
python tools/verify_corpus.py
python -m build
```

Les tests par défaut ne nécessitent ni compte ROMEO ni accès SSH. Leurs
identifiants et limites sont fictifs. `--live` active des suites qui peuvent
allouer des ressources et soumettre des jobs ; elles sont réservées aux essais
explicitement autorisés sur votre propre compte.

Le contrôle ciblé `python tests/run_all.py --only repro-live` soumet un petit
job CPU (1 cœur, 1 Go, 1 minute au maximum) et vérifie le calcul, la capture et
l’export par le protocole MCP. Son registre et ses rapports restent sous
`~/.romeo-mcp/test-runs/`. En cas d’interruption, utilisez
`python tests/smoke_repro_live.py --resume DOSSIER_DU_TEST` pour vérifier le
job existant sans en soumettre un autre.

## Avant un commit

- Utiliser l’adresse **noreply** indiquée dans les réglages Emails de GitHub,
  configurée avec `git config --local user.email "VOTRE_ADRESSE_NOREPLY"`.
- Choisir un pseudonyme public pour `git config --local user.name`.
- Ne jamais versionner votre profil ROMEO, vos clés, bases de jobs ou journaux
  de calcul. Utiliser des exemples inventés, même pour les messages d’erreur.
- Ajouter les fichiers explicitement et relire `git diff --cached`.
- Exécuter `python tools/check_privacy.py --staged` avant de committer, puis
  `python tools/check_privacy.py --history` avant de pousser.

Les hooks facultatifs automatisent ces contrôles sur votre poste :

```sh
git config --local core.hooksPath .githooks
```

Ils utilisent le Python du venv s’il existe. La CI répète les contrôles sur les
commits reçus. Ces règles détectent des motifs connus ; elles ne remplacent
pas la relecture et ne garantissent pas l’absence de toute donnée sensible.

## Périmètre d’une contribution

Chaque dossier versionné possède un README avec son rôle, un inventaire utile
et des liens vers sa section parente. Mettre cette navigation à jour lorsqu’un
dossier ou un parcours change, en partant de l’[index documentaire](docs/README.md).
Les guides du projet restent identifiés séparément des pages officielles ROMEO.

Décrivez le problème, la modification et les vérifications effectuées. Une
preuve hors ligne ne démontre pas qu’un calcul réel a réussi. Indiquez
séparément les essais sur le cluster, sans publier de compte, chemin personnel
ou données scientifiques non autorisées.

Conservez les mentions de droit d’auteur et le texte de licence lors de la
redistribution de parties substantielles du logiciel. Les modifications restent
permises selon MIT. Respectez aussi l’attribution des contenus tiers.

## Renouveler le corpus ROMEO

Préparez la collecte dans un dossier temporaire avec
`python tools/romeo_doc_scraper.py --output CHEMIN_TEMPORAIRE`, puis vérifiez le
contenu, les liens et la provenance avant de remplacer le corpus embarqué.
Relancez `tools/verify_corpus.py` et les tests documentaires, puis commitez
ensemble les pages, les images et le manifeste. Gardez les sources officielles
et leurs mentions ; ne leur attribuez pas la licence du code.
