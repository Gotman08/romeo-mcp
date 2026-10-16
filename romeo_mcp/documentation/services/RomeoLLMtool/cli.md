---
title: "Ligne de commande"
source: "https://romeo.univ-reims.fr/documentation/services/RomeoLLMtool/cli"
scraped_at: "2026-10-16 15:47:06"
---

[Sommaire](../../SOMMAIRE.md) › [Accueil](../../index.md) › [Services](../../services.md) › [RomeoLLMTool](../RomeoLLMtool.md) › Ligne de commande · [Corpus ROMEO](../../README.md) · [Guides MCP](https://github.com/Gotman08/romeo-mcp/blob/main/docs/README.md) · [Tools](https://github.com/Gotman08/romeo-mcp/blob/main/docs/Tools.md)

# Ligne de commande

Chaque action de l'interface terminal existe en sous-commande ; `romeollmtool <commande> --help` détaille les options de n'importe laquelle. Sans argument,
`romeollmtool` ouvre l'[interface terminal](../../services/RomeoLLMtool/gui.md).

## Démarrage rapide[​](#démarrage-rapide "Lien direct vers Démarrage rapide")

```bash
romeollmtool catalog list                                  # fiches disponibles
romeollmtool launch gemma4-e4b-sglang --project-code <code> # lancer un modèle
romeollmtool status                                         # suivre le job
romeollmtool chat gemma4-e4b-sglang                         # tester en direct
romeollmtool gateway start                                  # accès unifié (API OpenAI)
```

## `catalog` : parcourir le catalogue[​](#catalog--parcourir-le-catalogue "Lien direct vers catalog--parcourir-le-catalogue")

```bash
romeollmtool catalog list                       # catalogue + vos fiches perso
romeollmtool catalog list --category vision      # filtrer par catégorie
romeollmtool catalog show <fiche>                # fiche telle qu'elle sera lancée (fusion éventuelle)
```

La liste affiche moteur, modèle, ressources, validation, catégories,
licence et source (catalogue ou perso). Vos fiches perso sont dans
`~/.romeollmtool/configs/*.yaml` (format : [Écrire une fiche](../../services/RomeoLLMtool/fiches.md)).

## `launch` : lancer un modèle[​](#launch--lancer-un-modèle "Lien direct vers launch--lancer-un-modèle")

```bash
romeollmtool launch <fiche> --project-code <code> [options]
```

| Option | Rôle |
| --- | --- |
| `--project-code`, `--slurm-association` | code projet Slurm, **obligatoire** |
| `--config <fichier>` | fiche YAML explicite, prioritaire sur le catalogue |
| `--time` | durée max du job (24:00:00 au plus) |
| `--reservation` | réservation Slurm, sans modifier la fiche |
| `--dry-run` | affiche le script sans le soumettre |
| `--wait` / `--no-wait` | attendre que le serveur réponde (par défaut : oui) |

Avec `--wait` (défaut), la commande suit le job jusqu'à ce qu'il réponde et
affiche l'URL d'accès (gateway si active, sinon l'accès direct).

> ⚠️ **Attention**
>
> Lancer la même fiche plusieurs fois

Chaque appel crée un job Slurm distinct. `romeollmtool status` les affiche
tous sous le même nom de fiche, avec des numéros de job différents ; la
gateway répartit alors les requêtes tour à tour entre eux. `stop` et `logs`
refusent d'agir si le nom de fiche désigne plusieurs jobs : elles listent
les candidats et demandent de reprendre la commande avec le numéro de job
voulu. `endpoint`, lui, ne refuse rien : il affiche l'accès de chacun des
jobs correspondants, à la suite.

## `status` : vos jobs en cours[​](#status--vos-jobs-en-cours "Lien direct vers status--vos-jobs-en-cours")

```bash
romeollmtool status
```

Numéro de job, fiche, état, nœud, port, début (estimé si en attente), fin
prévue, moteur, modèle. Un job terminé reste affiché jusqu'à `romeollmtool stop <job>` (ses journaux restent lisibles).

## `stop` : arrêter un job[​](#stop--arrêter-un-job "Lien direct vers stop--arrêter-un-job")

```bash
romeollmtool stop <job|fiche>
romeollmtool stop --all
```

N'annule jamais un job qui n'est pas de vous ou pas lancé par romeollmtool.
Un numéro de job désigne un seul job sans ambiguïté ; un nom de fiche qui
correspond à plusieurs jobs (lancée plusieurs fois) est refusé : indiquer le
numéro de job voulu.

## `logs` : journaux d'un job[​](#logs--journaux-dun-job "Lien direct vers logs--journaux-dun-job")

```bash
romeollmtool logs <job|fiche>        # 50 dernières lignes, [out] et [err]
romeollmtool logs <job|fiche> -f     # suit en direct jusqu'à la fin du job
romeollmtool logs <job|fiche> -n 200
```

Sans argument, cible le seul job en cours s'il n'y en a qu'un.

## `endpoint` : comment joindre un modèle[​](#endpoint--comment-joindre-un-modèle "Lien direct vers endpoint--comment-joindre-un-modèle")

```bash
romeollmtool endpoint <job|fiche>
romeollmtool endpoint <job|fiche> --show-key   # affiche aussi la clé interne (débogage)
```

Affiche l'URL via la gateway (si active) et l'accès direct au job (pour
déboguer, avec sa clé interne).

## `verify` : vérifier une fiche[​](#verify--vérifier-une-fiche "Lien direct vers verify--vérifier-une-fiche")

```bash
romeollmtool verify <fiche> --account <code> [--time 01:00:00] [--keep] [--reservation <nom>]
```

Lance un vrai job (une heure maximum par défaut), teste qu'il répond
correctement (refus sans clé, modèle exposé, réponse à une question simple,
streaming, image si la fiche est en catégorie `vision`, ou l'endpoint direct
pour un type de fiche différent), puis l'arrête (`--keep` pour le garder) et
écrit un rapport dans `~/.romeollmtool/verify/<fiche>.json`. Une fiche du
catalogue est testée seule, sans votre override perso éventuel. Un rapport
réussi est ce qu'exige `romeollmtool-admin validate` pour promouvoir une
fiche dans le catalogue partagé.

## `chat` : tester un modèle[​](#chat--tester-un-modèle "Lien direct vers chat--tester-un-modèle")

```bash
romeollmtool chat                            # le seul modèle prêt, mode interactif
romeollmtool chat <fiche|modèle> -m "..."    # une question, sans mode interactif
romeollmtool chat <fiche> --think off        # sans réflexion ; low/medium/high/xhigh selon le modèle
romeollmtool chat <fiche> --hide-think --no-stream --max-tokens 500
```

Passe par la gateway (doit être démarrée). En mode interactif :
`/think <niveau>`, `/system <texte>`, `/reset`, `/show-think` /
`/hide-think`, `/exit` (aussi `/quit`, `/q`, Ctrl+D, ou deux fois Ctrl+C).
Ctrl+C pendant une réponse l'interrompt sans quitter.

## `engines` : moteurs partagés[​](#engines--moteurs-partagés "Lien direct vers engines--moteurs-partagés")

```bash
romeollmtool engines
```

Moteur, version, état (prêt ou incomplet), validation, date de construction.
Voir [Moteurs](../../services/RomeoLLMtool/engines.md).

## `doctor` : vérifier les permissions[​](#doctor--vérifier-les-permissions "Lien direct vers doctor--vérifier-les-permissions")

```bash
romeollmtool doctor          # ce qui ne va pas, et comment le corriger
romeollmtool doctor --fix    # corrige ce qui vous appartient (jamais le partagé)
```

Pour chaque problème : chemin concerné, à qui revient la correction (vous ou
un administrateur), et la commande exacte à lancer.

## `gateway` : accès unifié compatible OpenAI[​](#gateway--accès-unifié-compatible-openai "Lien direct vers gateway--accès-unifié-compatible-openai")

```bash
romeollmtool gateway start                  # URL affichée ; clé : gateway show-key
romeollmtool gateway start --port 11310 --hours 8
romeollmtool gateway status                 # URL, temps restant, modèles servis
romeollmtool gateway extend --hours 12      # repousse l'arrêt, sans redémarrer
romeollmtool gateway show-key
romeollmtool gateway rotate-key             # l'ancienne clé est refusée immédiatement
romeollmtool gateway stop                   # annule aussi vos jobs, sauf --keep-jobs
romeollmtool gateway logs -f
```

> ⚠️ **Warning**
>
> attention

`gateway stop` annule aussi tous vos jobs romeollmtool, sauf `--keep-jobs`.

Détails d'utilisation (routage, endpoints, exemples de clients) :
[Utiliser l'API](../../services/RomeoLLMtool/api.md).

## `stats` : votre usage[​](#stats--votre-usage "Lien direct vers stats--votre-usage")

```bash
romeollmtool stats
romeollmtool stats --days 30
```

GPU-heures (Slurm, toujours à jour) et nombre de requêtes (comptées par
votre gateway, absentes si vous avez appelé un job directement) par fiche.

## `version`[​](#version "Lien direct vers version")

```bash
romeollmtool version
```

---

← [Interface terminal](gui.md) | → [Écrire une fiche](fiches.md)

## Dans cette section

[↑ Haut de page](#ligne-de-commande) · [Sommaire officiel](../../SOMMAIRE.md) · [Guide du corpus](../../README.md)
