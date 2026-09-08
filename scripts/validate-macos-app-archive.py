#!/usr/bin/env python3
"""Validate and safely extract an Echo macOS updater archive.

Requires Python 3.12 or newer for ``tarfile.data_filter``. Validation completes
for every member before extraction begins. Relative symlinks used by macOS
framework bundles are preserved when their fully resolved targets stay inside
the archive.

Python tar extraction filters:
https://docs.python.org/3/library/tarfile.html#tarfile-extraction-filter
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import posixpath
import sys
import tarfile
import unicodedata


MINIMUM_PYTHON = (3, 12)


class ArchiveValidationError(ValueError):
    """The archive cannot be extracted without violating the trust boundary."""


def canonical_path(raw: str, *, label: str) -> str:
    if not raw or "\0" in raw:
        raise ArchiveValidationError(f"{label} is empty or contains NUL")
    path = PurePosixPath(raw)
    if path.is_absolute() or raw.startswith("/"):
        raise ArchiveValidationError(f"{label} is absolute: {raw!r}")
    normalized = posixpath.normpath(raw)
    if normalized in ("", "."):
        raise ArchiveValidationError(f"{label} addresses the extraction root: {raw!r}")
    if normalized == ".." or normalized.startswith("../"):
        raise ArchiveValidationError(f"{label} escapes the extraction root: {raw!r}")
    return normalized


def filesystem_key(path: str) -> str:
    # Default macOS filesystems are case-insensitive and normalize Unicode names.
    # Treat aliases that can overwrite each other there as duplicate members.
    return unicodedata.normalize("NFC", path).casefold()


def link_target(member_name: str, member: tarfile.TarInfo) -> str:
    raw_target = member.linkname
    if not raw_target or "\0" in raw_target:
        raise ArchiveValidationError(f"link target is empty or contains NUL: {member_name!r}")
    if PurePosixPath(raw_target).is_absolute() or raw_target.startswith("/"):
        raise ArchiveValidationError(f"link target is absolute: {member_name!r} -> {raw_target!r}")
    if member.issym():
        combined = posixpath.join(posixpath.dirname(member_name), raw_target)
    else:
        # POSIX tar hard-link names are rooted at the archive root.
        combined = raw_target
    return canonical_path(combined, label=f"link target for {member_name!r}")


def resolve_links(path: str, links: dict[str, str]) -> str:
    current = path
    visited: set[str] = set()
    while True:
        if current in visited:
            raise ArchiveValidationError(f"link cycle resolves through {current!r}")
        visited.add(current)
        parts = current.split("/")
        replacement: tuple[str, str] | None = None
        for index in range(1, len(parts) + 1):
            prefix = "/".join(parts[:index])
            if prefix in links:
                suffix = "/".join(parts[index:])
                replacement = (links[prefix], suffix)
                break
        if replacement is None:
            return current
        target, suffix = replacement
        combined = posixpath.join(target, suffix) if suffix else target
        current = canonical_path(combined, label=f"resolved link path for {path!r}")


def validate_members(members: list[tarfile.TarInfo]) -> None:
    by_name: dict[str, tarfile.TarInfo] = {}
    member_indexes: dict[str, int] = {}
    filesystem_names: dict[str, str] = {}
    filesystem_prefixes: dict[str, str] = {}
    links: dict[str, str] = {}

    for index, member in enumerate(members):
        name = canonical_path(member.name, label="archive member")
        key = filesystem_key(name)
        if name in by_name:
            raise ArchiveValidationError(f"duplicate archive member: {name!r}")
        if key in filesystem_names:
            raise ArchiveValidationError(
                f"members collide on macOS: {filesystem_names[key]!r} and {name!r}"
            )
        if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
            raise ArchiveValidationError(f"unsupported archive member type: {name!r}")
        parts = name.split("/")
        for prefix_index in range(1, len(parts) + 1):
            prefix = "/".join(parts[:prefix_index])
            prefix_key = filesystem_key(prefix)
            existing_prefix = filesystem_prefixes.get(prefix_key)
            if existing_prefix is not None and existing_prefix != prefix:
                raise ArchiveValidationError(
                    f"path prefixes collide on macOS: {existing_prefix!r} and {prefix!r}"
                )
            filesystem_prefixes[prefix_key] = prefix
        by_name[name] = member
        member_indexes[name] = index
        filesystem_names[key] = name
        if member.issym() or member.islnk():
            links[name] = link_target(name, member)

    names = set(by_name)
    for name, member in by_name.items():
        parts = name.split("/")
        for index in range(1, len(parts)):
            parent = "/".join(parts[:index])
            if parent in by_name and not by_name[parent].isdir():
                raise ArchiveValidationError(
                    f"archive member is nested below a non-directory: {name!r} below {parent!r}"
                )

        if not (member.issym() or member.islnk()):
            continue
        resolved = resolve_links(links[name], links)
        target_exists = resolved in names or any(path.startswith(f"{resolved}/") for path in names)
        if not target_exists:
            raise ArchiveValidationError(
                f"link target is absent from archive: {name!r} -> {resolved!r}"
            )
        if member.islnk():
            direct_target = links[name]
            if direct_target not in by_name or not by_name[direct_target].isfile():
                raise ArchiveValidationError(
                    f"hard-link target is not a regular archive member: "
                    f"{name!r} -> {direct_target!r}"
                )
            if member_indexes[direct_target] >= member_indexes[name]:
                raise ArchiveValidationError(
                    f"hard-link target must precede its link: {name!r} -> {direct_target!r}"
                )


def verify_extracted_tree(destination: Path) -> None:
    root = destination.resolve(strict=True)
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        for name in (*directory_names, *file_names):
            path = Path(directory, name)
            resolved = path.resolve(strict=False)
            if not resolved.is_relative_to(root):
                raise ArchiveValidationError(
                    f"extracted path resolves outside evidence directory: {path} -> {resolved}"
                )


def validate_and_extract(archive_path: Path, destination: Path) -> None:
    if sys.version_info < MINIMUM_PYTHON:
        raise ArchiveValidationError("Python 3.12 or newer is required")
    if not archive_path.is_file():
        raise ArchiveValidationError(f"archive not found: {archive_path}")
    if destination.exists():
        if not destination.is_dir() or any(destination.iterdir()):
            raise ArchiveValidationError(f"destination must be an empty directory: {destination}")
    else:
        destination.mkdir(parents=True)

    with tarfile.open(archive_path, mode="r:*") as archive:
        members = archive.getmembers()
        if not members:
            raise ArchiveValidationError("archive is empty")
        validate_members(members)
        # Run the standard-library safety filter across the complete member set
        # before creating any archive content. extractall applies it again while
        # performing the real extraction.
        for member in members:
            tarfile.data_filter(member, str(destination))
        archive.extractall(destination, members=members, filter=tarfile.data_filter)

    verify_extracted_tree(destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        validate_and_extract(args.archive, args.destination)
    except (ArchiveValidationError, OSError, tarfile.TarError) as error:
        print(f"error: archive rejected: {error}", file=sys.stderr)
        return 1
    print(f"archive validated and safely extracted: {args.destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
