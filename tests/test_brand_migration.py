from pathlib import Path

import brand_migration
from brand import BRAND


class FakeCredentialError(Exception):
    pass


class FakeStore:
    CredentialError = FakeCredentialError

    def __init__(self, values=None, fail_write=False):
        self.values = dict(values or {})
        self.fail_write = fail_write
        self.deleted = []

    def read_target(self, target):
        return self.values.get(target, "")

    def write_target(self, target, value):
        if self.fail_write:
            raise self.CredentialError("no")
        self.values[target] = value

    def delete_target(self, target):
        self.deleted.append(target)
        self.values.pop(target, None)


def test_storage_migration_is_missing_only_and_idempotent(tmp_path):
    old_config = tmp_path / "old-config"
    old_data = tmp_path / "old-data"
    new_config = tmp_path / "new-config"
    new_data = tmp_path / "new-data"
    old_config.mkdir()
    old_data.mkdir()
    new_config.mkdir()
    (old_config / "config.json").write_text("old", encoding="utf-8")
    (old_data / "history.jsonl").write_text("history", encoding="utf-8")
    (new_config / "config.json").write_text("new", encoding="utf-8")

    assert brand_migration.migrate_storage(old_config, new_config, old_data, new_data) == 1
    assert (new_config / "config.json").read_text(encoding="utf-8") == "new"
    assert (new_data / "history.jsonl").read_text(encoding="utf-8") == "history"
    assert brand_migration.migrate_storage(old_config, new_config, old_data, new_data) == 0
    assert (old_data / "history.jsonl").exists()


def test_credential_is_verified_before_legacy_is_deleted(tmp_path):
    store = FakeStore({BRAND.legacy_credential_target: "secret"})
    result = brand_migration.migrate(tmp_path / "a", tmp_path / "b",
                                     tmp_path / "c", tmp_path / "d", store)
    assert result.credential_migrated
    assert store.values[BRAND.credential_target] == "secret"
    assert BRAND.legacy_credential_target in store.deleted


def test_existing_new_credential_wins_and_failed_copy_preserves_legacy():
    store = FakeStore({BRAND.credential_target: "new",
                       BRAND.legacy_credential_target: "old"})
    assert not brand_migration.migrate_credential(store)
    assert store.values[BRAND.legacy_credential_target] == "old"
    failing = FakeStore({BRAND.legacy_credential_target: "old"}, fail_write=True)
    try:
        brand_migration.migrate_credential(failing)
    except FakeCredentialError:
        pass
    assert failing.values[BRAND.legacy_credential_target] == "old"
    assert not failing.deleted
