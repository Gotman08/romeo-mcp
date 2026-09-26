"""Filtrage des donnees sensibles avant export d'une fiche partageable."""

import re


REDACTED = "[REDACTED]"
_NAME = r"[\w.-]*(?:password|passwd|passphrase|secret|token|credential|authorization|cookie|api[_-]?key|access[_-]?key|private[_-]?key)[\w.-]*"
_KEY = re.compile(_NAME, re.I)
_PRIVATE = re.compile(r"-----BEGIN (?:[A-Z ]+)?PRIVATE KEY-----.*?(?:-----END (?:[A-Z ]+)?PRIVATE KEY-----|\Z)", re.S)
_TOKEN = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}|xox[baprs]-[A-Za-z0-9-]{10,})\b")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_URL_AUTH = re.compile(r"(https?://)[^\s/@]+:[^\s/@]+@", re.I)
_SIGNED_URL = re.compile(r"https?://[^\s<>\"']*[?&](?:token|key|sig|signature|x-amz-[\w-]+|x-goog-[\w-]+)=[^\s<>\"']*", re.I)
_BEARER = re.compile(r"\b(?:Bearer|Basic)\s+[A-Za-z0-9+/=._-]+", re.I)
_VALUE = r'''(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s;,]+)'''
_ASSIGN = re.compile(r"(?P<key>\b" + _NAME + r"[\"']?\s*[:=]\s*)" + _VALUE, re.I)
_OPTION = re.compile(r"(?P<key>--?" + _NAME + r"(?:=|\s+))" + _VALUE, re.I)
_HEREDOC = re.compile(r"<<-?\s*[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?")


def sensitive_path(value: str) -> bool:
    parts = value.replace("\\", "/").lower().split("/")
    return any(p in {".ssh", ".aws", ".azure", ".kube", "hosts.yml"}
               or p.startswith((".env", "id_rsa", "id_ed25519", "id_ecdsa"))
               or p.endswith((".pem", ".key", ".p12", ".pfx"))
               or _KEY.search(p) for p in parts)


def redact_text(value: str) -> str:
    # Filtrer les continuations avant de remplacer les valeurs : remplacer un
    # antislash d'affectation trop tot ferait perdre la ligne suivante.
    parts = []
    continuation = False
    for line in value.splitlines(keepends=True):
        continued = line.rstrip().endswith("\\")
        if continuation or (continued and _KEY.search(line)):
            parts.append("# " + REDACTED + ("\n" if line.endswith("\n") else ""))
            continuation = continued
        else:
            parts.append(line)
    value = "".join(parts)
    value = _PRIVATE.sub(REDACTED, value)
    value = _TOKEN.sub(REDACTED, value)
    value = _JWT.sub(REDACTED, value)
    value = _SIGNED_URL.sub(REDACTED, value)
    value = _URL_AUTH.sub(r"\1[REDACTED]@", value)
    value = _BEARER.sub(REDACTED, value)
    # Une valeur entre guillemets peut s'etendre sur plusieurs lignes.
    value = _ASSIGN.sub(lambda m: m.group("key") + REDACTED, value)
    value = _OPTION.sub(lambda m: m.group("key") + REDACTED, value)
    lines = []
    delimiter = None
    sensitive_continuation = False
    for line in value.splitlines(keepends=True):
        ending = "\n" if line.endswith("\n") else ""
        if delimiter:
            if line.strip().strip("\t") == delimiter:
                delimiter = None
                lines.append(line)
            else:
                lines.append("# " + REDACTED + ending)
            continue
        match = _HEREDOC.search(line)
        if match:
            # Un corps heredoc est opaque (JSON, cle, script embarque...).
            delimiter = match.group(1)
        sensitive_line = bool(_KEY.search(line)) or sensitive_continuation
        continuation = line.rstrip().endswith("\\")
        if sensitive_line:
            lines.append("# " + REDACTED + ending)
        else:
            lines.append(line)
        sensitive_continuation = sensitive_line and continuation
    return "".join(lines)


def sanitize(value):
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {redact_text(str(k)): REDACTED if _KEY.search(str(k)) else sanitize(v)
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v) for v in value]
    return value
