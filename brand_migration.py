"""Idempotent migration from the legacy Verbatim local identity."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import uuid

from brand import BRAND
import credential_store


@dataclass(frozen=True)
class MigrationResult:
    copied_files: int = 0
    credential_migrated: bool = False
    warnings: tuple[str, ...] = ()


def _copy_missing_file(source: Path, target: Path) -> bool:
    if target.exists() or not source.is_file():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.migrate-{uuid.uuid4().hex}.tmp")
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, target)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return True


def _copy_missing_tree(source: Path, target: Path) -> int:
    if not source.is_dir():
        return 0
    copied = 0
    for path in source.rglob("*"):
        if path.is_file():
            copied += int(_copy_missing_file(path, target / path.relative_to(source)))
    return copied


def migrate_storage(legacy_config_dir: Path, config_dir: Path,
                    legacy_data_dir: Path, data_dir: Path) -> int:
    copied = _copy_missing_tree(legacy_config_dir, config_dir)
    copied += _copy_missing_tree(legacy_data_dir, data_dir)
    return copied


def migrate_credential(store=credential_store) -> bool:
    """Copy and verify the secret before deleting the legacy credential."""
    if store.read_target(BRAND.credential_target):
        return False
    legacy = store.read_target(BRAND.legacy_credential_target)
    if not legacy:
        return False
    store.write_target(BRAND.credential_target, legacy)
    if store.read_target(BRAND.credential_target) != legacy:
        raise store.CredentialError("WordArc credential verification failed")
    store.delete_target(BRAND.legacy_credential_target)
    return True


def migrate(legacy_config_dir: Path, config_dir: Path,
            legacy_data_dir: Path, data_dir: Path,
            store=credential_store) -> MigrationResult:
    warnings = []
    copied = 0
    credential_migrated = False
    try:
        copied = migrate_storage(legacy_config_dir, config_dir,
                                 legacy_data_dir, data_dir)
    except OSError as exc:
        warnings.append(f"storage migration failed: {type(exc).__name__}")
    try:
        credential_migrated = migrate_credential(store)
    except store.CredentialError as exc:
        warnings.append(f"credential migration failed: {type(exc).__name__}")
    return MigrationResult(copied, credential_migrated, tuple(warnings))
