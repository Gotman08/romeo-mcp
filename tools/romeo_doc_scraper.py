#!/usr/bin/env python3
"""
ROMEO Documentation Scraper
===========================
Télécharge toute la documentation du supercalculateur ROMEO (URCA)
en format Markdown avec images locales.

Auteur: Collecte de la documentation publique ROMEO
Usage: python romeo_doc_scraper.py [--output OUTPUT_DIR]
"""

import os
import re
import sys
import time
import hashlib
import json
import argparse
import tempfile
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Set, Dict, Optional, Tuple
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup, Tag
from markdownify import markdownify as md, MarkdownConverter


# =============================================================================
# Configuration
# =============================================================================

BASE_URL = "https://romeo.univ-reims.fr"
DOC_ROOT = "/documentation"
START_URL = f"{BASE_URL}{DOC_ROOT}/"

DEFAULT_OUTPUT = str(Path(__file__).resolve().parents[1] / "romeo_mcp" / "documentation")

# Headers pour éviter d'être bloqué
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RomeoDocScraper/1.0; Educational Purpose)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/*,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

# Extensions d'images supportées
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico"}

# Délai entre requêtes (politesse)
REQUEST_DELAY = 0.3


def write_atomic(path: Path, content: bytes) -> None:
    """Un lecteur actif voit une page complete, jamais une ecriture partielle."""
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".romeo-", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


# =============================================================================
# Custom Markdown Converter
# =============================================================================

class RomeoMarkdownConverter(MarkdownConverter):
    """Convertisseur Markdown personnalisé pour la doc Romeo."""
    
    def __init__(self, image_map: Dict[str, str], **kwargs):
        super().__init__(**kwargs)
        self.image_map = image_map
    
    def convert_img(self, el, text, *args, **kwargs):
        """Convertit les images en utilisant les chemins locaux."""
        src = el.get("src", "")
        alt = el.get("alt", "")
        title = el.get("title", "")
        
        # Utiliser le chemin local si disponible
        if src in self.image_map:
            src = self.image_map[src]
        
        if title:
            return f'![{alt}]({src} "{title}")'
        return f'![{alt}]({src})'
    
    def convert_pre(self, el, text, *args, **kwargs):
        """Améliore la conversion des blocs de code.

        Deux pièges Docusaurus/Prism sont traités ici :
        - le langage est porté par le <pre> (classe `language-bash`), pas
          seulement par le <code> ;
        - chaque ligne de code est enveloppée dans un
          `<span class="token-line">` SANS retour à la ligne. Un simple
          get_text() collerait tout le script sur une seule ligne, ce qui rend
          les exemples de soumission inutilisables.
        """
        code_el = el.find("code")
        target = code_el if code_el else el

        # Le langage peut être annoncé sur le <code>, sur le <pre>, ou sur le
        # conteneur parent selon la version du thème.
        lang = ""
        candidates = [code_el, el, el.parent, getattr(el.parent, "parent", None)]
        for node in candidates:
            if node is None or not hasattr(node, "get"):
                continue
            for cls in node.get("class", []) or []:
                if cls.startswith("language-"):
                    lang = cls.replace("language-", "")
                    break
            if lang:
                break

        line_spans = target.find_all("span", class_="token-line")
        if line_spans:
            code_text = "\n".join(span.get_text() for span in line_spans)
        else:
            code_text = target.get_text()

        return f"\n```{lang}\n{code_text.rstrip()}\n```\n"
    
    def convert_div(self, el, text, *args, **kwargs):
        """Gère les divs spéciales (admonitions Docusaurus)."""
        classes = el.get("class", [])
        
        # Détection des admonitions Docusaurus
        admonition_types = {
            "admonition-note": "📝 **Note**",
            "admonition-tip": "💡 **Tip**",
            "admonition-info": "ℹ️ **Info**",
            "admonition-caution": "⚠️ **Attention**",
            "admonition-warning": "⚠️ **Warning**",
            "admonition-danger": "🚨 **Danger**",
            "theme-admonition-caution": "⚠️ **Attention**",
            "theme-admonition-warning": "⚠️ **Warning**",
            "alert": "⚠️ **Attention**",
        }
        
        for cls in classes:
            if cls in admonition_types:
                return f"\n\n> {admonition_types[cls]}\n> \n> {text.strip()}\n\n"
        
        return text


def convert_html_to_markdown(html: str, image_map: Dict[str, str]) -> str:
    """Convertit HTML en Markdown avec gestion des images locales."""
    converter = RomeoMarkdownConverter(
        image_map=image_map,
        heading_style="atx",
        bullets="-",
        code_language="",
        strip=["script", "style", "nav", "footer", "header"],
    )
    return converter.convert(html)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SidebarItem:
    """Une entrée de la barre latérale Docusaurus."""
    level: int
    label: str
    url: str
    is_category: bool


@dataclass
class PageInfo:
    """Informations sur une page de documentation."""
    url: str
    title: str
    content_html: str
    images: Set[str] = field(default_factory=set)
    links: Set[str] = field(default_factory=set)
    # Éléments de navigation, reconstruits après le passage complet.
    sidebar: list = field(default_factory=list)
    breadcrumbs: list = field(default_factory=list)
    prev: Optional[Tuple[str, str]] = None
    next: Optional[Tuple[str, str]] = None
    filepath: Optional[Path] = None


@dataclass
class ScraperStats:
    """Statistiques du scraping."""
    pages_scraped: int = 0
    images_downloaded: int = 0
    errors: int = 0
    start_time: float = field(default_factory=time.time)
    
    def duration(self) -> float:
        return time.time() - self.start_time


# =============================================================================
# Scraper Principal
# =============================================================================

class RomeoDocScraper:
    """Scraper pour la documentation Romeo."""
    
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.images_dir = self.output_dir / "images"
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        
        self.visited_urls: Set[str] = set()
        self.pages: list = []  # conserve pour reconstruire la navigation
        self.image_map: Dict[str, str] = {}  # URL originale -> chemin local
        self.stats = ScraperStats()
        
        # Créer les dossiers
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
    
    def normalize_url(self, url: str, base_url: str = BASE_URL) -> Optional[str]:
        """Normalise une URL relative ou absolue."""
        if not url:
            return None
        
        # Ignorer les ancres pures, javascript, mailto
        if url.startswith(("#", "javascript:", "mailto:", "tel:")):
            return None
        
        # Construire l'URL absolue
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/"):
            url = base_url + url
        elif not url.startswith("http"):
            url = urllib.parse.urljoin(base_url + "/", url)
        
        # Parser et reconstruire pour normaliser
        parsed = urllib.parse.urlparse(url)
        
        # Supprimer le fragment
        url = urllib.parse.urlunparse(parsed._replace(fragment=""))
        
        # Supprimer le trailing slash sauf pour la racine
        if url.endswith("/") and url != START_URL:
            url = url.rstrip("/")
        
        return url
    
    def is_doc_url(self, url: str) -> bool:
        """Vérifie si l'URL fait partie de la documentation."""
        if not url:
            return False
        parsed = urllib.parse.urlparse(url)
        return (
            parsed.netloc == "romeo.univ-reims.fr" and
            parsed.path.startswith("/documentation")
        )
    
    def is_image_url(self, url: str) -> bool:
        """Vérifie si l'URL pointe vers une image."""
        if not url:
            return False
        parsed = urllib.parse.urlparse(url)
        ext = Path(parsed.path).suffix.lower()
        return ext in IMAGE_EXTENSIONS
    
    def fetch_page(self, url: str) -> Optional[str]:
        """Récupère le contenu HTML d'une page."""
        try:
            time.sleep(REQUEST_DELAY)
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            # requests retombe sur ISO-8859-1 quand l'en-tête HTTP ne précise
            # aucun charset, ce qui transforme l'UTF-8 du site en mojibake
            # ("Ã©tant" au lieu de "étant").
            if not response.encoding or response.encoding.lower() == "iso-8859-1":
                response.encoding = response.apparent_encoding or "utf-8"
            return response.text
        except requests.RequestException as e:
            print(f"  ❌ Erreur fetch {url}: {e}")
            self.stats.errors += 1
            return None
    
    def download_image(self, url: str) -> Optional[str]:
        """Télécharge une image et retourne le chemin local relatif."""
        if url in self.image_map:
            return self.image_map[url]
        
        try:
            # Normaliser l'URL
            full_url = self.normalize_url(url)
            if not full_url:
                return None
            
            time.sleep(REQUEST_DELAY / 2)
            response = self.session.get(full_url, timeout=30)
            response.raise_for_status()
            
            # Générer un nom de fichier unique basé sur l'URL
            parsed = urllib.parse.urlparse(full_url)
            original_name = Path(parsed.path).name
            
            # Utiliser un hash pour éviter les collisions
            url_hash = hashlib.md5(full_url.encode()).hexdigest()[:8]
            
            # Extraire l'extension
            ext = Path(original_name).suffix.lower()
            if not ext or ext not in IMAGE_EXTENSIONS:
                # Essayer de détecter depuis le content-type
                content_type = response.headers.get("content-type", "")
                if "png" in content_type:
                    ext = ".png"
                elif "jpeg" in content_type or "jpg" in content_type:
                    ext = ".jpg"
                elif "gif" in content_type:
                    ext = ".gif"
                elif "svg" in content_type:
                    ext = ".svg"
                else:
                    ext = ".png"  # Par défaut
            
            # Nom final
            safe_name = re.sub(r'[^\w\-.]', '_', Path(original_name).stem)
            filename = f"{safe_name}_{url_hash}{ext}"
            
            # Sauvegarder
            filepath = self.images_dir / filename
            write_atomic(filepath, response.content)
            
            # Chemin relatif pour le markdown
            relative_path = f"images/{filename}"
            self.image_map[url] = relative_path
            self.image_map[full_url] = relative_path
            
            self.stats.images_downloaded += 1
            return relative_path
            
        except Exception as e:
            print(f"  ⚠️  Erreur image {url}: {e}")
            return url  # Garder l'URL originale en cas d'échec
    
    def parse_page(self, url: str, html: str) -> PageInfo:
        """Parse une page HTML et extrait les informations."""
        soup = BeautifulSoup(html, "html.parser")

        # La navigation est lue AVANT tout nettoyage : selon la page, le
        # conteneur principal peut englober le fil d'Ariane, qui serait alors
        # supprimé par la purge des <nav>.
        sidebar = self.extract_sidebar(soup)
        breadcrumbs = self.extract_breadcrumbs(soup)
        prev_link, next_link = self.extract_pagination(soup)

        # Extraire le titre
        title = "Documentation"
        title_el = soup.find("h1")
        if title_el:
            title = title_el.get_text(strip=True)
        else:
            title_el = soup.find("title")
            if title_el:
                title = title_el.get_text(strip=True).split("|")[0].strip()
        
        # Trouver le contenu principal (Docusaurus)
        main_content = (
            soup.find("article") or
            soup.find("main") or
            soup.find(class_="markdown") or
            soup.find(class_="docMainContainer") or
            soup.find(class_="container")
        )
        
        if not main_content:
            main_content = soup.body if soup.body else soup
        
        # Nettoyer le contenu
        # Supprimer la navigation, sidebar, footer
        for el in main_content.find_all(["nav", "footer", "aside"]):
            el.decompose()
        
        # Supprimer les éléments de navigation Docusaurus
        for cls in ["pagination-nav", "theme-doc-sidebar", "table-of-contents", 
                    "tocCollapsible", "breadcrumbs", "navbar"]:
            for el in main_content.find_all(class_=cls):
                el.decompose()
        
        # Extraire les liens vers d'autres pages de doc.
        # On balaie `soup` entier et non `main_content` : sur un site Docusaurus
        # la quasi-totalite des liens internes vit dans la barre de navigation
        # et la barre laterale, qui sont hors du contenu principal.
        links = set()
        for a in soup.find_all("a", href=True):
            href = self.normalize_url(a["href"])
            if href and self.is_doc_url(href):
                links.add(href)
        
        # Extraire et télécharger les images
        images = set()
        for img in main_content.find_all("img", src=True):
            src = img["src"]
            images.add(src)
            
            # Télécharger l'image
            local_path = self.download_image(src)
            if local_path:
                img["src"] = local_path
        
        # Aussi les images en background-image dans style
        for el in main_content.find_all(style=True):
            style = el["style"]
            urls = re.findall(r'url\(["\']?([^)"\']+)["\']?\)', style)
            for url in urls:
                if self.is_image_url(url):
                    images.add(url)
                    self.download_image(url)
        
        return PageInfo(
            url=url,
            title=title,
            content_html=str(main_content),
            images=images,
            links=links,
            sidebar=sidebar,
            breadcrumbs=breadcrumbs,
            prev=prev_link,
            next=next_link,
        )

    # -- extraction de la navigation Docusaurus ------------------------------
    def extract_sidebar(self, soup) -> list:
        """Lit la barre latérale : libellés officiels, hiérarchie et ordre.

        Docusaurus n'affiche entièrement que la branche de la page courante ;
        les autres catégories restent repliées et leurs enfants absents du
        HTML. La structure complète s'obtient donc en fusionnant les barres
        latérales de toutes les pages, ce que fait :meth:`build_navigation`.
        """
        menu = soup.find("ul", class_="theme-doc-sidebar-menu")
        if not menu:
            return []

        items = []
        for li in menu.find_all("li"):
            classes = " ".join(li.get("class") or [])
            match = re.search(r"level-(\d+)", classes)
            if not match:
                continue
            link = li.find("a", href=True)
            if not link:
                continue
            url = self.normalize_url(link["href"])
            if not url or not self.is_doc_url(url):
                continue
            items.append(
                SidebarItem(
                    level=int(match.group(1)),
                    label=link.get_text(strip=True),
                    url=url,
                    is_category="item-category" in classes,
                )
            )
        return items

    def extract_breadcrumbs(self, soup) -> list:
        """Fil d'Ariane de la page, sous forme de couples (libellé, url)."""
        nav = soup.find("nav", class_="theme-doc-breadcrumbs")
        if not nav:
            return []

        trail = []
        for el in nav.find_all(class_="breadcrumbs__link"):
            label = el.get_text(strip=True)
            href = el.get("href") if el.name == "a" else None
            url = self.normalize_url(href) if href else None
            if not label and url:
                label = "Accueil"
            if label:
                trail.append((label, url if url and self.is_doc_url(url) else None))
        return trail

    def extract_pagination(self, soup):
        """Liens « précédent » et « suivant » proposés par Docusaurus."""
        nav = soup.find("nav", class_="pagination-nav")
        if not nav:
            return None, None

        found = {}
        for link in nav.find_all("a", href=True):
            classes = " ".join(link.get("class") or [])
            label_el = link.find(
                class_=lambda c: c and "pagination-nav__label" in " ".join(
                    c if isinstance(c, list) else [c]
                )
            )
            label = label_el.get_text(strip=True) if label_el else link.get_text(strip=True)
            url = self.normalize_url(link["href"])
            if not url or not self.is_doc_url(url):
                continue
            sens = "prev" if "--prev" in classes else "next"
            found[sens] = (label, url)
        return found.get("prev"), found.get("next")
    
    def url_to_filepath(self, url: str) -> Path:
        """Convertit une URL en chemin de fichier Markdown."""
        parsed = urllib.parse.urlparse(url)
        path = parsed.path
        
        # Supprimer /documentation/ du début
        path = path.replace("/documentation", "", 1)
        
        # Nettoyer le chemin
        path = path.strip("/")
        
        if not path:
            path = "index"
        
        # Décoder les caractères URL encodés
        path = urllib.parse.unquote(path)
        
        # Remplacer les caractères problématiques
        path = re.sub(r'[<>:"|?*]', '_', path)
        
        # Ajouter .md
        if not path.endswith(".md"):
            path = path + ".md"
        
        return self.output_dir / path
    
    def save_page(self, page: PageInfo) -> Path:
        """Sauvegarde une page en Markdown."""
        filepath = self.url_to_filepath(page.url)
        
        # Créer les dossiers parents si nécessaire
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # Convertir en Markdown
        markdown = convert_html_to_markdown(page.content_html, self.image_map)
        
        # Nettoyer le markdown. Le chemin du fichier est necessaire pour
        # calculer des liens relatifs corrects depuis les sous-repertoires.
        markdown = self.clean_markdown(markdown, filepath)
        
        # Ajouter un header avec métadonnées
        header = f"""---
title: "{page.title}"
source: "{page.url}"
scraped_at: "{time.strftime('%Y-%m-%d %H:%M:%S')}"
---

"""
        
        # Sauvegarder
        write_atomic(filepath, (header + markdown).encode("utf-8"))
        
        return filepath
    
    def clean_markdown(self, markdown: str, filepath: Path) -> str:
        """Nettoie le markdown généré.

        `filepath` sert à produire des liens réellement relatifs : une page
        rangée dans `ressources/romeo_2025/` doit pointer vers `../../images/`
        et non vers `images/`, sinon toutes les cibles sont mortes.
        """
        # Octets NUL parasites laissés par un caractère multi-octets tronqué :
        # ils font classer le fichier comme binaire et le rendent invisible aux
        # outils de recherche.
        markdown = markdown.replace("\x00", "")

        # Supprimer les lignes vides multiples
        markdown = re.sub(r'\n{4,}', '\n\n\n', markdown)

        # Supprimer les espaces en fin de ligne
        markdown = re.sub(r' +$', '', markdown, flags=re.MULTILINE)

        # Profondeur de la page dans l'arborescence du corpus.
        try:
            depth = len(filepath.relative_to(self.output_dir).parts) - 1
        except ValueError:
            depth = 0
        prefix = "../" * depth

        # Corriger les liens vers d'autres pages de doc
        def fix_link(match):
            text = match.group(1)
            url = match.group(2)

            if url.startswith("/documentation"):
                new_url = url.replace("/documentation/", "").replace("/documentation", "")
                # Une URL de répertoire (`services/Oratio/`) correspond au
                # fichier d'index `services/Oratio.md`, pas à `.../.md`.
                new_url = new_url.rstrip("/")
                if not new_url:
                    new_url = "index"
                if not new_url.endswith(".md"):
                    new_url += ".md"
                return f"[{text}]({prefix}{new_url})"

            return match.group(0)

        markdown = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', fix_link, markdown)

        # Les chemins d'images produits par `image_map` sont relatifs à la
        # racine du corpus : les rebaser sur la position réelle de la page.
        if prefix:
            markdown = re.sub(
                r'(!\[[^\]]*\]\()images/', r'\1' + prefix + 'images/', markdown
            )
        
        # Supprimer les lignes "Sur cette page" et tables des matières auto
        markdown = re.sub(r'^Sur cette page\s*$', '', markdown, flags=re.MULTILINE)
        
        return markdown.strip()
    
    # -- reconstruction de la navigation -------------------------------------
    def corpus_key(self, url: str) -> Optional[str]:
        """Identifiant d'une page dans le corpus : son chemin relatif en .md.

        Passer par le fichier plutôt que par l'URL fusionne naturellement les
        variantes `/page` et `/page/`, qui désignent la même page.
        """
        full = self.normalize_url(url)
        if not full or not self.is_doc_url(full):
            return None
        return self.url_to_filepath(full).relative_to(self.output_dir).as_posix()

    @staticmethod
    def md_target(chemin: str) -> str:
        """Encadre une cible de lien qui contient des caractères gênants.

        Plusieurs pages ont un nom contenant une espace (« Architecture
        Aarch64.md ») : sans les chevrons de CommonMark, le lien est tronqué à
        la première espace.
        """
        return "<{}>".format(chemin) if any(c in chemin for c in " ()") else chemin

    def rel_link(self, key: str, from_path: Path) -> str:
        """Lien markdown relatif vers la page `key` depuis `from_path`."""
        target = self.output_dir / key
        rel = os.path.relpath(target, from_path.parent).replace(os.sep, "/")
        return self.md_target(rel)

    def build_navigation(self) -> None:
        """Reconstruit la navigation du corpus et l'injecte dans les pages.

        Docusaurus ne rend que la branche ouverte de sa barre latérale : aucune
        page ne contient l'arborescence complète. On fusionne donc les barres de
        toutes les pages visitées, ce qui reconstitue l'arbre officiel avec ses
        libellés et son ordre, puis on écrit un sommaire et on greffe sur chaque
        page son fil d'Ariane, ses enfants et sa pagination.
        """
        print()
        print("🧭 Reconstruction de la navigation…")

        labels: Dict[str, str] = {}
        parent_of: Dict[str, Optional[str]] = {}
        order: list = []

        for page in self.pages:
            stack: Dict[int, str] = {}
            for item in page.sidebar:
                key = self.corpus_key(item.url)
                if not key:
                    continue
                labels.setdefault(key, item.label)
                # Refermer les niveaux au moins aussi profonds avant de
                # déterminer le parent.
                for level in [l for l in list(stack) if l >= item.level]:
                    del stack[level]
                if key not in parent_of:
                    parent_of[key] = stack.get(item.level - 1)
                    order.append(key)
                stack[item.level] = key

        children: Dict[Optional[str], list] = {}
        for key in order:
            children.setdefault(parent_of.get(key), []).append(key)

        self.nav_labels = labels
        self.nav_children = children

        self.write_summary(labels, children)

        # Une même page a pu être atteinte par plusieurs URL : on ne réécrit
        # chaque fichier qu'une fois.
        uniques: Dict[str, PageInfo] = {}
        for page in self.pages:
            if page.filepath:
                uniques[page.filepath.as_posix()] = page

        touchees = 0
        for page in uniques.values():
            if self.inject_navigation(page, labels, children):
                touchees += 1

        total = sum(len(v) for v in children.values())
        print(f"   ✅ {total} entrée(s) d'arborescence, {touchees} page(s) enrichie(s)")

    def write_summary(self, labels: Dict[str, str], children: Dict) -> None:
        """Écrit `SOMMAIRE.md`, point d'entrée unique du corpus."""
        lines = [
            "# Documentation ROMEO : sommaire",
            "",
            "Arborescence reconstruite depuis la barre latérale officielle du site.",
            "",
        ]
        vus: Set[str] = set()

        def render(key: str, depth: int) -> None:
            if key in vus:
                return
            vus.add(key)
            label = labels.get(key, key.rsplit("/", 1)[-1][:-3])
            lines.append(
                "{}- [{}]({})".format("  " * depth, label, self.md_target(key))
            )
            for enfant in children.get(key, []):
                render(enfant, depth + 1)

        for racine in children.get(None, []):
            render(racine, 0)

        orphelines = sorted(
            p.relative_to(self.output_dir).as_posix()
            for p in self.output_dir.rglob("*.md")
            if p.relative_to(self.output_dir).as_posix() not in vus
            and p.name not in ("SOMMAIRE.md", "README.md")
        )
        if orphelines:
            lines += [
                "",
                "## Pages hors arborescence",
                "",
                "Présentes dans le corpus mais absentes de la barre latérale officielle.",
                "",
            ]
            lines += ["- [{}]({})".format(o, self.md_target(o)) for o in orphelines]

        lines.append("")
        write_atomic(self.output_dir / "SOMMAIRE.md", "\n".join(lines).encode("utf-8"))
        print(f"   📑 SOMMAIRE.md : {len(vus)} page(s) dans l'arbre, "
              f"{len(orphelines)} hors arbre")

    def inject_navigation(self, page: PageInfo, labels: Dict, children: Dict) -> bool:
        """Greffe fil d'Ariane, sous-pages et pagination sur une page."""
        path = page.filepath
        if path is None or not path.exists():
            return False

        texte = path.read_text(encoding="utf-8")
        key = path.relative_to(self.output_dir).as_posix()

        # Fil d'Ariane, avec un retour vers le sommaire en tête.
        fil = ["[Sommaire]({})".format(self.rel_link("SOMMAIRE.md", path))]
        for label, url in page.breadcrumbs:
            cible = self.corpus_key(url) if url else None
            if cible and cible != key:
                fil.append("[{}]({})".format(label, self.rel_link(cible, path)))
            else:
                fil.append(label)
        entete = " › ".join(fil)

        # Insertion juste après le front matter.
        match = re.match(r"^(---\n.*?\n---\n)", texte, flags=re.S)
        if match:
            debut, corps = match.group(1), texte[match.end():]
        else:
            debut, corps = "", texte

        # Les blocs sont assemblés avec une ligne vide entre eux : sans elle,
        # le séparateur `---` de la pagination transformerait la dernière ligne
        # du corps en titre setext.
        blocs = [entete, corps.strip("\n")]

        # Sous-pages : c'est ce qui manquait aux pages de catégorie, vides
        # parce que Docusaurus rend leurs cartes en JavaScript.
        enfants = children.get(key, [])
        if enfants:
            liste = [
                "- [{}]({})".format(
                    labels.get(c, c.rsplit("/", 1)[-1][:-3]), self.rel_link(c, path)
                )
                for c in enfants
            ]
            blocs.append("## Dans cette section\n\n" + "\n".join(liste))

        liens_pagination = []
        for sens, valeur in (("←", page.prev), ("→", page.next)):
            if not valeur:
                continue
            label, url = valeur
            cible = self.corpus_key(url)
            if cible:
                liens_pagination.append(
                    "{} [{}]({})".format(sens, label, self.rel_link(cible, path))
                )
        if liens_pagination:
            blocs.append("---\n\n" + " | ".join(liens_pagination))

        write_atomic(path, (debut + "\n" + "\n\n".join(b for b in blocs if b) + "\n").encode("utf-8"))
        return True

    def load_sitemap(self) -> Set[str]:
        """Récupère la liste exhaustive des pages depuis le sitemap Docusaurus.

        La découverte par liens dépend de la structure du thème et rate
        facilement des pages ; le sitemap, lui, est la liste officielle.
        """
        sitemap_url = f"{BASE_URL}{DOC_ROOT}/sitemap.xml"
        try:
            response = self.session.get(sitemap_url, timeout=30)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"⚠️  Sitemap indisponible ({e})")
            print("   Repli sur la seule découverte par liens.")
            return set()

        urls = set()
        for loc in re.findall(r"<loc>([^<]+)</loc>", response.text):
            normalized = self.normalize_url(loc.strip())
            if normalized and self.is_doc_url(normalized):
                urls.add(normalized)

        print(f"🗺️  Sitemap : {len(urls)} page(s) référencée(s)")
        return urls

    def scrape(self) -> None:
        """Lance le scraping complet."""
        print("=" * 60)
        print("🚀 ROMEO Documentation Scraper")
        print("=" * 60)
        print(f"📁 Dossier de sortie: {self.output_dir.absolute()}")
        print(f"🌐 URL de départ: {START_URL}")
        print()
        
        # File d'URLs à visiter : le sitemap fournit la liste exhaustive, la
        # découverte par liens ne sert plus que de filet de sécurité.
        to_visit = {START_URL}
        to_visit.update(self.load_sitemap())
        print(f"📋 {len(to_visit)} page(s) à traiter au départ")
        print()
        
        while to_visit:
            url = min(to_visit)
            to_visit.remove(url)
            
            if url in self.visited_urls:
                continue
            
            self.visited_urls.add(url)
            
            print(f"📄 [{self.stats.pages_scraped + 1}] {url}")
            
            # Récupérer la page
            html = self.fetch_page(url)
            if not html:
                continue
            
            # Parser
            page = self.parse_page(url, html)
            
            # Sauvegarder
            filepath = self.save_page(page)
            page.filepath = filepath
            self.pages.append(page)
            print(f"   ✅ Sauvegardé: {filepath.relative_to(self.output_dir)}")
            
            self.stats.pages_scraped += 1
            
            # Ajouter les nouveaux liens à visiter
            new_links = page.links - self.visited_urls
            to_visit.update(new_links)
            
            if new_links:
                print(f"   🔗 {len(new_links)} nouveau(x) lien(s) trouvé(s)")
        
        self.build_navigation()
        self.print_summary()
        self.write_manifest()

    def write_manifest(self) -> None:
        """Conserve la provenance et les empreintes du corpus versionne."""
        files = {
            path.relative_to(self.output_dir).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(self.output_dir.rglob("*"))
            if path.is_file() and path.name != "manifest.json"
        }
        manifest = {
            "source": START_URL,
            "publisher": "Universite de Reims Champagne-Ardenne (URCA)",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "pages": len({p.filepath for p in self.pages if p.filepath}),
            "images": self.stats.images_downloaded,
            "errors": self.stats.errors,
            "files": files,
        }
        write_atomic(self.output_dir / "manifest.json",
                     (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    
    def print_summary(self) -> None:
        """Affiche le résumé du scraping."""
        print()
        print("=" * 60)
        print("📊 RÉSUMÉ")
        print("=" * 60)
        print(f"✅ Pages téléchargées:  {self.stats.pages_scraped}")
        print(f"🖼️  Images téléchargées: {self.stats.images_downloaded}")
        print(f"❌ Erreurs:             {self.stats.errors}")
        print(f"⏱️  Durée:               {self.stats.duration():.1f}s")
        print()
        print(f"📁 Documentation sauvegardée dans: {self.output_dir.absolute()}")
        print()
        
        # Créer un fichier README
        self.create_readme()
    
    def create_readme(self) -> None:
        """Crée un fichier README dans le dossier de sortie."""
        readme_content = f"""# Documentation ROMEO - Supercalculateur URCA

Cette documentation a été téléchargée depuis le site officiel du Centre de Calcul Régional ROMEO.

**Point d'entrée : [SOMMAIRE.md](SOMMAIRE.md)** : arborescence complète,
reconstruite depuis la barre latérale officielle du site.

## Source

- **Site officiel**: {BASE_URL}
- **Documentation**: {START_URL}

## Statistiques

- **Pages**: {len({p.filepath for p in self.pages if p.filepath})}
- **Images**: {self.stats.images_downloaded}
- **Date de téléchargement**: {time.strftime('%Y-%m-%d %H:%M:%S')}

## Structure

```
{self.output_dir.name}/
├── README.md              # Ce fichier
├── index.md               # Page d'accueil de la documentation
├── images/                # Images téléchargées
│   └── ...
├── creation_compte.md     # Accès au portail
├── ressources/            # Ressources de calcul
│   └── ...
├── services/              # Services disponibles
│   └── ...
└── ...
```

## Utilisation

Vous pouvez:
1. Lire les fichiers `.md` avec n'importe quel éditeur de texte
2. Les visualiser avec un viewer Markdown (VS Code, Obsidian, etc.)
3. Les convertir en HTML ou PDF avec Pandoc

## Notes

- Les images sont stockées localement dans le dossier `images/`
- Les liens internes ont été convertis en liens relatifs
- Certains éléments interactifs peuvent ne pas fonctionner hors-ligne

## Licence

Cette documentation appartient à l'Université de Reims Champagne-Ardenne (URCA).
Téléchargée à des fins éducatives et de consultation hors-ligne.
"""
        
        readme_path = self.output_dir / "README.md"
        write_atomic(readme_path, readme_content.encode("utf-8"))
        print(f"📝 README créé: {readme_path}")


# =============================================================================
# Point d'entrée
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Télécharge la documentation ROMEO en Markdown",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  python romeo_doc_scraper.py
  python romeo_doc_scraper.py --output ~/Documents/romeo_docs
        """
    )
    
    parser.add_argument(
        "-o", "--output",
        default=DEFAULT_OUTPUT,
        help=f"Dossier de sortie (défaut: {DEFAULT_OUTPUT})"
    )
    
    args = parser.parse_args()
    
    # Vérifier les dépendances
    try:
        import requests
        from bs4 import BeautifulSoup
        from markdownify import markdownify
    except ImportError as e:
        print("❌ Dépendances manquantes!")
        print("   Installez-les avec:")
        print("   pip install requests beautifulsoup4 markdownify")
        sys.exit(1)
    
    # Lancer le scraping
    scraper = RomeoDocScraper(args.output)
    
    try:
        scraper.scrape()
        if scraper.stats.errors:
            raise SystemExit("Collecte incomplete : consulter les erreurs avant de publier le corpus.")
    except KeyboardInterrupt:
        print("\n\n⚠️ Interruption utilisateur")
        scraper.print_summary()
        sys.exit(1)


if __name__ == "__main__":
    main()
