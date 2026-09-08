#!/usr/bin/env python3
"""Verify Tauri updater artifacts against the public key in tauri.conf.json."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


TRUSTED_COMMENT = re.compile(r"trusted comment: timestamp:[1-9][0-9]*\tfile:(.+)")


class VerificationError(ValueError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decode_public_key(config_path: Path) -> bytes:
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        encoded = config["plugins"]["updater"]["pubkey"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise VerificationError(f"cannot read updater public key from {config_path}: {error}")
    if not isinstance(encoded, str) or not encoded:
        raise VerificationError("updater public key must be a non-empty Base64 string")
    try:
        decoded = base64.b64decode(encoded, validate=True)
        text = decoded.decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as error:
        raise VerificationError(f"updater public key is not strict Base64 UTF-8: {error}")
    lines = text.splitlines()
    if len(lines) != 2 or not lines[0].startswith("untrusted comment: minisign public key"):
        raise VerificationError("updater public key is not a two-line Minisign public key")
    return decoded


def decode_signature(signature_path: Path, expected_signed_name: str) -> bytes:
    try:
        encoded = signature_path.read_bytes()
        decoded = base64.b64decode(encoded, validate=True)
        text = decoded.decode("utf-8")
    except (OSError, binascii.Error, UnicodeDecodeError) as error:
        raise VerificationError(f"invalid Tauri signature {signature_path}: {error}")
    lines = text.splitlines()
    if len(lines) != 4:
        raise VerificationError(f"signature must contain exactly four Minisign lines: {signature_path}")
    match = TRUSTED_COMMENT.fullmatch(lines[2])
    if match is None or match.group(1) != expected_signed_name:
        actual = match.group(1) if match else "<malformed>"
        raise VerificationError(
            f"signed filename mismatch for {signature_path}: expected {expected_signed_name!r}, got {actual!r}"
        )
    return decoded


def verify(args: argparse.Namespace) -> dict[str, object]:
    minisign = shutil.which("minisign")
    if minisign is None:
        raise VerificationError("minisign executable is required")
    if len(args.pair) != 4:
        raise VerificationError("exactly four updater artifact/signature pairs are required")
    if args.evidence_dir.exists():
        if not args.evidence_dir.is_dir() or any(args.evidence_dir.iterdir()):
            raise VerificationError(f"evidence directory must be empty: {args.evidence_dir}")
    else:
        args.evidence_dir.mkdir(parents=True)

    public_key_path = args.evidence_dir / "updater.pub"
    public_key_path.write_bytes(decode_public_key(args.config))
    seen_paths: set[Path] = set()
    evidence: list[dict[str, str]] = []
    for index, (expected_name, artifact_raw, signature_raw) in enumerate(args.pair):
        artifact = Path(artifact_raw).resolve(strict=True)
        signature = Path(signature_raw).resolve(strict=True)
        if artifact in seen_paths or signature in seen_paths or artifact == signature:
            raise VerificationError("artifact and signature paths must be unique")
        seen_paths.update((artifact, signature))
        decoded_signature = args.evidence_dir / f"signature-{index}.minisig"
        decoded_signature.write_bytes(decode_signature(signature, expected_name))
        result = subprocess.run(
            [
                minisign,
                "-V",
                "-p",
                str(public_key_path),
                "-m",
                str(artifact),
                "-x",
                str(decoded_signature),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise VerificationError(f"Minisign rejected {artifact.name}: {detail}")
        evidence.append(
            {
                "artifact": artifact.name,
                "artifact_sha256": sha256(artifact),
                "signature": signature.name,
                "signature_sha256": sha256(signature),
                "signed_filename": expected_name,
            }
        )
    return {
        "public_key_sha256": sha256(public_key_path),
        "pairs": evidence,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument(
        "--pair",
        action="append",
        nargs=3,
        metavar=("SIGNED_FILENAME", "ARTIFACT", "SIGNATURE"),
        default=[],
    )
    args = parser.parse_args()
    try:
        evidence = verify(args)
        args.output_json.write_text(json.dumps(evidence, sort_keys=True) + "\n", encoding="utf-8")
    except (VerificationError, OSError) as error:
        print(f"error: updater signature verification failed: {error}", file=sys.stderr)
        return 1
    print(f"four Tauri updater signatures verified; evidence retained: {args.evidence_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
