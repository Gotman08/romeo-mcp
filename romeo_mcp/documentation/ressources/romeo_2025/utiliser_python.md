---
title: "Utiliser Python"
source: "https://romeo.univ-reims.fr/documentation/ressources/romeo_2025/utiliser_python"
scraped_at: "2026-09-26 02:37:06"
---

[Sommaire](../../SOMMAIRE.md) › [Accueil](../../index.md) › [Ressources de calcul](../../ressources.md) › [Romeo 2025](../romeo_2025.md) › Utiliser Python · [Corpus ROMEO](../../README.md) · [Guides MCP](https://github.com/Gotman08/romeo-mcp/blob/main/docs/README.md) · [Tools](https://github.com/Gotman08/romeo-mcp/blob/main/docs/Tools.md)

# Utiliser Python

## Via Spack[​](#via-spack "Lien direct vers Via Spack")

### Charger des modules Python[​](#charger-des-modules-python "Lien direct vers Charger des modules Python")

Il s'agit de la méthode principale pour utiliser Python sur Romeo2025.

Il faut pour cela chercher les paquets des modules Python via Spack que vous souhaitez utiliser, en précisant comme dépendance le paquet de l'exécutable Python souhaité (rappel : vous pouvez utiliser les options `--variants` et `--long` pour mieux afficher quels options sont disponibles pour les paquets installés).

spack find --variants --long py-numpy ^python@3.8.19
```bash
-- linux-rhel9-zen4 / aocc@5.0.0 --------------------------------
4z6ciws py-numpy@1.24.4 build_system=python_pip patches=873745d
==> 1 installed package
```

Chargez ensuite le paquet en précisant le même python en dépendance, en utilisant son hash pour être certain d'utiliser le bon exécutable python :

`spack load py-numpy ^python@3.8.19/zcpokjg`

> ⚠️ **Warning**
>
> attention

Veillez à bien utiliser une unique installation de python (et de ne charger les modules ne correspondant qu'à une unique installation de python, avec un hash unique) pour éviter les erreurs lors de l'exécution de certains programmes.

Vous pouvez ensuite vérifier que vous n'avez qu'un seul exécutable Python de chargé :

spack find --loaded --long --deps | grep python@
```bash
zcpokjg             python@3.8.19
zcpokjg     python@3.8.19
```

### En cas de chargement de plusieurs exécutables Python[​](#en-cas-de-chargement-de-plusieurs-exécutables-python "Lien direct vers En cas de chargement de plusieurs exécutables Python")

Si plusieurs lignes apparaissent avec des hash différents, cela signifie que plusieurs exécutables pythons ont été chargés, ce qui peut causer des problèmes :

spack find --loaded --long --deps | grep python@
```bash
zcpokjg     python@3.8.19
wdxjcri python@3.13.0
```

Si cela arrive, il faut revoir les paquets Spack précédemment chargés, ne retenir que ceux dépendant d'un unique exécutable Python, décharger les paquets dépendant des autres exécutables Python, et installer les paquets des modules python manquant.

spack find --loaded --long --deps | grep -E '^\w+ \w|python@'
```bash
w6sdz5d apptainer@1.3.4
zcpokjg             python@3.8.19
vzvuz6h petsc@3.22.1
wdxjcri     python@3.13.0
4z6ciws py-numpy@1.24.4
zcpokjg     python@3.8.19
```

`spack unload`

`spack install petsc ^python@3.8.19/zcpokjg`

`spack load apptainer petsc py-numpy ^python@3.8.19/zcpokjg`

## Via les environnements virtuels Python[​](#via-les-environnements-virtuels-python "Lien direct vers Via les environnements virtuels Python")

### Installer un nouvel environnement virtuel Python[​](#installer-un-nouvel-environnement-virtuel-python "Lien direct vers Installer un nouvel environnement virtuel Python")

Les utilisateurs peuvent également installer manuellement des environnements virtuels python dans leur propre dossier utilisateur (« `/home/nom_utilisateur/` »). Pour cela, il faut suivre plusieurs étapes :

1. Créer le dossier qui contiendra l'environnement virtuel :
   `mkdir <nom_dossier>`
2. (Optionnel) Installer un pip avec la version de python souhaitée :
   `spack install py-pip ^python@X.Y.Z`
3. Charger un module pip correspondant à la version de python souhaitée :
   `spack load py-pip ^python@X.Y.Z/lehash`
4. Créer l'environnement python :
   `python -m venv <nom_dossier>`
5. Charger l'environnement python :
   `source <nom_dossier>/bin/activate`
6. Installer les paquets python :
   `python -m pip install <noms_paquets>`
7. Quand l'utilisation de python est terminée, décharger l'environnement python :
   `deactivate`

Exemple :

```bash
romeo_load_x64cpu_env
mkdir -p mes_environnements_python/mon_env_python
spack load py-pip ^python@3.8.19/zcpokjg
python -m venv mes_environnements_python/mon_env_python
source mes_environnements_python/mon_env_python/bin/activate
python -m pip install numpy matplotlib
```

### Utiliser un environnement virtuel Python[​](#utiliser-un-environnement-virtuel-python "Lien direct vers Utiliser un environnement virtuel Python")

1. Charger le module python correspondant :
   `spack load py-pip ^python@X.Y.Z/lehash`
2. Charger l'environnement virtuel :
   `source <nom_dossier>/bin/activate`
3. Quand l'utilisation de python est terminée, décharger l'environnement python :
   `deactivate`

Exemple :

```bash
romeo_load_x64cpu_env
spack load py-pip ^python@3.8.19/zcpokjg
source mes_environnements_python/mon_env_python/bin/activate
```

---

← [Installer un logiciel](installer_un_logiciel.md) | → [Utiliser OpenMPI](utiliser_openmpi.md)

## Dans cette section

[↑ Haut de page](#utiliser-python) · [Sommaire officiel](../../SOMMAIRE.md) · [Guide du corpus](../../README.md)
