"""Verifie des attestations Sigstore dans l'environnement isole du verificateur.

Lance avec `python -I` : aucun module du paquet n'est importe. Ni l'API GitHub ni
le stockage des bundles ne sont de confiance. Seules la racine Sigstore, l'identite
du workflow et l'empreinte de la wheel decident.
"""
import argparse
import json
from pathlib import Path
import sys

ISSUER = "https://token.actions.githubusercontent.com"
PROVENANCE = "https://slsa.dev/provenance/v1"
MAX_BUNDLE = 16 * 1024 * 1024


def decode_snappy(data: bytes) -> bytes:
    """Format bloc Snappy, seul format servi par le stockage de GitHub."""
    size, shift, index = 0, 0, 0
    while True:
        byte = data[index]
        index += 1
        size |= (byte & 0x7f) << shift
        if byte < 0x80:
            break
        shift += 7
        if shift > 28:
            raise ValueError("taille Snappy invalide")
    if size > MAX_BUNDLE:
        raise ValueError("bundle trop volumineux")
    output = bytearray()
    while index < len(data):
        tag = data[index]
        index += 1
        kind = tag & 3
        if kind == 0:
            length = tag >> 2
            if length >= 60:
                width = length - 59
                length = int.from_bytes(data[index:index + width], "little")
                index += width
            length += 1
            output += data[index:index + length]
            index += length
        else:
            if kind == 1:
                length = 4 + ((tag >> 2) & 7)
                offset = ((tag & 0xe0) << 3) | data[index]
                index += 1
            else:
                width = 2 if kind == 2 else 4
                length = (tag >> 2) + 1
                offset = int.from_bytes(data[index:index + width], "little")
                index += width
            if not 0 < offset <= len(output) or len(output) + length > size:
                raise ValueError("copie Snappy invalide")
            for _ in range(length):
                output.append(output[-offset])
        if len(output) > size:
            raise ValueError("bundle plus long qu'annonce")
    if len(output) != size:
        raise ValueError("bundle tronque")
    return bytes(output)


def verify(bundles: list[bytes], digest: str, identity: str) -> dict:
    """Une seule attestation valide suffit : les autres peuvent etre etrangeres."""
    from sigstore.models import Bundle
    from sigstore.verify import Verifier, policy

    verifier = Verifier.production()
    expected = policy.Identity(identity=identity, issuer=ISSUER)
    failures = []
    for raw in bundles:
        try:
            bundle = Bundle.from_json(raw if raw[:1] == b"{" else decode_snappy(raw))
            payload_type, payload = verifier.verify_dsse(bundle, expected)
            statement = json.loads(payload)
            if payload_type != "application/vnd.in-toto+json" or statement.get("predicateType") != PROVENANCE:
                raise ValueError("attestation qui n'est pas une provenance SLSA v1")
            subjects = [item.get("name") for item in statement["subject"]
                        if item.get("digest", {}).get("sha256") == digest]
            if not subjects:
                raise ValueError("empreinte absente de l'attestation")
            return {"ok": True, "identity": identity, "issuer": ISSUER, "subject": subjects[0],
                    "predicate_type": PROVENANCE, "sha256": digest}
        except Exception as exc:  # noqa: BLE001 - toute anomalie refuse ce bundle
            failures.append("{}: {}".format(type(exc).__name__, str(exc)[:300]))
    return {"ok": False, "error": " ; ".join(failures)[:2000] or "aucune attestation"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--digest", required=True)
    parser.add_argument("--identity", required=True)
    parser.add_argument("bundles", nargs="+", type=Path)
    args = parser.parse_args()
    result = verify([path.read_bytes() for path in args.bundles], args.digest, args.identity)
    print(json.dumps(result))
    if not result["ok"]:
        print(result["error"], file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
