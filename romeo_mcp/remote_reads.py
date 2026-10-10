"""Sondes de fichiers en JSON, autonomes et bornees (stdlib distante seule)."""
from .remote_paths import CONFINED_PATHS

# Le format humain de ls ne conserve ni les LF des noms ni les noms de liens.
# nsmallest ne conserve que limit+1 entrees en memoire, sans liste recursive.
LIST_DIRECTORY = CONFINED_PATHS + r'''
import base64, heapq, json, os, stat, sys
from datetime import datetime
path, limit = sys.argv[1], int(sys.argv[2])
roots = json.loads(sys.argv[3])
directory = None
try:
    directory = confined_open(path, roots, os.O_RDONLY | os.O_DIRECTORY)
    with os.scandir(directory) as scan:
        selected = heapq.nsmallest(limit + 1, scan, key=lambda entry: entry.name)
    entries = []
    for entry in selected[:limit]:
        info = entry.stat(follow_symlinks=False)
        raw_name = os.fsencode(entry.name)
        name = raw_name.decode("utf-8", "replace")
        item = {"name": name, "size": str(info.st_size),
                "modified": datetime.fromtimestamp(info.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "is_dir": stat.S_ISDIR(info.st_mode),
                "is_symlink": stat.S_ISLNK(info.st_mode)}
        if name != entry.name:
            # Les surrogates POSIX ne sont pas du texte UTF-8 valide pour MCP.
            # Garder aussi les octets exacts, sans faire echouer tout le dossier.
            item["name_bytes_base64"] = base64.b64encode(raw_name).decode("ascii")
        entries.append(item)
    print(json.dumps({"entries": entries, "truncated": len(selected) > limit}, ensure_ascii=True))
except OSError as exc:
    print(json.dumps({"error": str(exc)}, ensure_ascii=True))
    sys.exit(2)
finally:
    if directory is not None:
        os.close(directory)
'''

# Ne jamais lire une ligne entiere sans borne : elle peut faire plusieurs Go.
# Le decodage incremental preserve l'UTF-8 aux frontieres des blocs. Seule la
# tranche demandee est conservee, plus un caractere pour prouver la troncature.
READ_TEXT = CONFINED_PATHS + r'''
import codecs, json, sys
path, offset, limit, budget = sys.argv[1], *map(int, sys.argv[2:5])
roots = json.loads(sys.argv[5])
decoder = codecs.getincrementaldecoder("utf-8")("replace")
line, size, last = 1, 0, None
pieces = []
def consume(text):
    global line, size
    segments = text.split("\n")
    for index, segment in enumerate(segments):
        newline = index < len(segments) - 1
        piece = segment + ("\n" if newline else "")
        if offset <= line < offset + limit and size <= budget:
            kept = piece[:budget + 1 - size]
            pieces.append(kept)
            size += len(kept)
        if newline:
            line += 1
try:
    with os.fdopen(confined_open(path, roots, os.O_RDONLY), "rb") as stream:
        while True:
            block = stream.read(65536)
            if not block:
                break
            last = block[-1]
            consume(decoder.decode(block))
        consume(decoder.decode(b"", final=True))
    content = "".join(pieces)
    print(json.dumps({"content": content[:budget], "truncated": len(content) > budget,
                      "total_lines": str(line - 1 + int(last is not None and last != 10))},
                     ensure_ascii=True))
except OSError as exc:
    print(json.dumps({"error": str(exc)}, ensure_ascii=True))
    sys.exit(2)
'''
