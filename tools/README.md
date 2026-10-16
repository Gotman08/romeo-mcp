# Utilitaires du projet

[Accueil](../README.md) › [Documentation](../docs/README.md) › Utilitaires

Ces scripts accompagnent l’installation et la maintenance du dépôt. Ils se
lancent depuis la **racine du projet**, avec le Python du venv activé. Pour
soumettre un calcul, utiliser les [outils MCP](../docs/Tools.md).

<details>
<summary>Sommaire de cette page</summary>

- [Choisir le bon script](#choisir-le-bon-script)
- [Enregistrer le MCP dans un client](#enregistrer-le-mcp-dans-un-client)
- [Vérifier avant de publier](#vérifier-avant-de-publier)
- [Renouveler la documentation ROMEO](#renouveler-la-documentation-romeo)
- [Continuer](#continuer)

</details>

## Choisir le bon script

| Script | Usage | Effets |
|---|---|---|
| [install_mcp.py](install_mcp.py) | Enregistrer le serveur dans un client IA | Peut modifier les fichiers personnels du client, avec sauvegarde préalable |
| [check_privacy.py](check_privacy.py) | Vérifier les contenus qui seront publiés | Lit l’index Git et, sur demande, l’historique ; affiche les emplacements signalés |
| [verify_corpus.py](verify_corpus.py) | Contrôler la copie documentaire | Lit les liens, images, ancres, casse des noms de fichiers, accès depuis le sommaire et empreintes du manifeste |
| [prepare_release.py](prepare_release.py) | Préparer une release stable | Vérifie le tag et les distributions puis écrit les empreintes et notes dans `dist/` |
| [romeo_doc_scraper.py](romeo_doc_scraper.py) | Renouveler la copie du site ROMEO | Accède au site officiel et écrit dans le dossier de sortie choisi |
| [merge_corpus.py](merge_corpus.py) | Intégrer une collecte au corpus versionné | Compare sans rien écrire ; avec `--write`, met à jour le corpus puis le vérifie |

## Enregistrer le MCP dans un client

```sh
python tools/install_mcp.py --list
python tools/install_mcp.py --targets codex --dry-run
python tools/install_mcp.py --targets codex
```

Les cibles sont `codex`, `claude-code` et `claude-desktop`. Une liste séparée
par des virgules permet d’en choisir plusieurs. `--dry-run` montre les
changements prévus ; sans cette option, le script enregistre la configuration
et vérifie le démarrage du serveur. Le relancer met à jour la même entrée.

L’installateur reprend automatiquement les préférences d’approbation de Codex
et conserve les choix explicites pour Romeo, ses règles par outil et ses outils
désactivés. `--follow-client-approvals` remplace un ancien choix global propre
à Romeo par les préférences enregistrées du client. Claude Code applique ses
propres règles d’autorisation, que l’installateur conserve. Le calcul est refait
à chaque exécution de l’installateur ; voir les
[règles de reprise des préférences](../docs/configuration.md#reprendre-automatiquement-les-préférences-du-client).

Le projet Slurm se règle séparément avec `python -m romeo_mcp configure`.
Les options `--python`, `--name` et les fichiers de configuration explicites
sont détaillés par `python tools/install_mcp.py --help`.
Voir aussi la [configuration des clients](../docs/configuration.md#autres-clients-stdio).

## Vérifier avant de publier

```sh
python tools/check_privacy.py --staged
python tools/check_privacy.py --history
python tools/verify_corpus.py
```

Le contrôle de confidentialité lit **l’index**, c’est-à-dire les fichiers
préparés avec `git add`. `--staged` vérifie aussi l’identité du prochain
commit ; `--history` parcourt les objets accessibles depuis les références Git.
Un signalement produit un code de sortie non nul et doit être examiné avant
publication. Ce contrôle cible des motifs connus.

`verify_corpus.py` accepte aussi un dossier en argument, par exemple une
collecte avant intégration. Il contrôle les cibles de liens et d’images avec la
**casse exacte** des noms de fichiers (un lien correct sous Windows ou macOS est
mort sous Linux, donc dans la CI), les ancres `#fragment`, qui doivent désigner
un titre de la page visée, les octets parasites, les empreintes du manifeste et
l’accès à chaque page depuis le sommaire.

Les [hooks locaux](../.githooks/README.md) et la
[CI GitHub](../.github/workflows/README.md) utilisent ces mêmes vérifications.

## Renouveler la documentation ROMEO

Pour publier une nouvelle version du code et du corpus, suivre le
[parcours de release](../docs/updates.md#publier-une-nouvelle-version).

Installer les dépendances facultatives avec `python -m pip install -e ".[docs]"`,
puis choisir un dossier temporaire extérieur au dépôt :

```sh
python tools/romeo_doc_scraper.py --output CHEMIN_TEMPORAIRE
python tools/verify_corpus.py CHEMIN_TEMPORAIRE
python tools/merge_corpus.py CHEMIN_TEMPORAIRE
python tools/merge_corpus.py CHEMIN_TEMPORAIRE --write
```

Le collecteur écrit les pages officielles brutes ; `merge_corpus.py` les intègre
au corpus versionné. Sans `--write`, il compare et n’écrit rien.

Le collecteur normalise lui-même les liens que le site publie mal formés. Quand
la source Markdown amont laisse des crochets autour d’une cible
(`[texte]([https://…])`), Docusaurus sert `/documentation/[https://…]`, une
adresse qui n’existe pas. Le collecteur retire les crochets, puis :

| Contenu des crochets | Lien produit |
|---|---|
| Page de la documentation | lien local `page.md`, ancre après l’extension (`page.md#section`) |
| Autre URL `http(s)` | lien externe, repris tel quel |
| Adresse de courriel | `mailto:adresse` |

Ces fausses cibles ne sont pas téléchargées : `errors` dans `manifest.json` ne
compte que de vrais échecs. Chaque normalisation est consignée par page dans la
rubrique `link_normalization` du manifeste (href amont → cible retenue). Un
contenu de crochets inexploitable garde l’adresse du site et est compté dans
`errors`, ce qui fait échouer la commande en fin de collecte au lieu de masquer
le défaut.

`merge_corpus.py` ajoute aux pages brutes la navigation propre au projet :

| Ajout | Détail |
|---|---|
| Fil d’Ariane | suffixe vers le guide du corpus, les guides MCP et le catalogue des outils |
| Pied de page | « Dans cette section », avec retour en haut de page, au sommaire et au guide du corpus |
| Ancres des titres | un id imposé par le site (`#article1`) devient l’ancre calculée depuis le titre, dans le titre comme dans les liens qui le visent, car GitHub et les lecteurs Markdown ignorent l’id du site |
| Sommaire | l’en-tête et le pied écrits à la main entourent l’arborescence officielle |
| Manifeste | provenance de la collecte, empreintes de tous les fichiers, inventaire des README et `local_anchor_repairs` |

Les README de section écrits à la main ne sont jamais modifiés. L’outil refuse
une collecte qui signale des erreurs, qui ne passe pas `verify_corpus.py` ou qui
contient déjà cette navigation, et il ne supprime les pages et images disparues
du site qu’avec `--prune`. Les dates de collecte (`scraped_at`, `retrieved_at`)
n’entrent pas dans la comparaison : le code de sortie est 0 quand le corpus
correspond déjà à la collecte. Le suffixe du fil d’Ariane renvoie vers
`docs/README.md` et `docs/Tools.md` du dépôt ; si ces adresses changent,
modifier les constantes `GUIDES_MCP` et `TOOLS` de l’outil, puis relancer la
fusion pour réécrire toutes les pages.

Après `--write` :

1. Relire le README du corpus : date de collecte et décomptes du tableau de
   provenance (l’outil signale un décompte périmé), puis les README de section
   dont les sections officielles ont changé.
2. Vérifier la recherche locale avec les
   [suites documentaires](../tests/README.md#suites-hors-ligne).
3. Publier ensemble les pages, les images, le sommaire et le manifeste.

La date de collecte décrit les pages officielles. La navigation ajoutée par
le projet reste identifiée séparément dans le [README du corpus](../romeo_mcp/documentation/README.md).

## Continuer

[Installer et démarrer](../README.md#prise-en-main) ·
[Contribuer](../CONTRIBUTING.md) ·
[Comprendre le code](../romeo_mcp/README.md)

---

[↑ Haut de page](#utilitaires-du-projet) · [Accueil](../README.md) · [Documentation](../docs/README.md) · [Catalogue Tools](../docs/Tools.md)
