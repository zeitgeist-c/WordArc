from unittest import mock

import pytest

import credential_store


def test_read_all_preserves_order_and_deduplicates():
    values = {
        credential_store.TARGETS[0]: "primary",
        credential_store.TARGETS[1]: "backup",
        credential_store.TARGETS[2]: "primary",
    }
    with mock.patch.object(
        credential_store, "read_target",
        side_effect=lambda target: values.get(target, ""),
    ):
        assert credential_store.read_all() == ["primary", "backup"]


def test_write_all_uses_only_fixed_targets_and_clears_unused_slots():
    state = {target: "old" for target in credential_store.TARGETS}

    def write(target, secret):
        state[target] = secret

    def delete(target):
        state[target] = ""

    with mock.patch.object(credential_store, "read_target",
                           side_effect=lambda target: state[target]), \
         mock.patch.object(credential_store, "write_target", side_effect=write), \
         mock.patch.object(credential_store, "delete_target", side_effect=delete):
        credential_store.write_all(["one", "two"])
    assert [state[target] for target in credential_store.TARGETS] == [
        "one", "two", "", "", "",
    ]


def test_write_all_rolls_back_every_slot_after_partial_failure():
    before = {
        target: ("old-primary" if index == 0 else "old-backup" if index == 1 else "")
        for index, target in enumerate(credential_store.TARGETS)
    }
    state = dict(before)
    failed = {"once": False}

    def write(target, secret):
        if (target == credential_store.TARGETS[1]
                and secret == "new-backup" and not failed["once"]):
            failed["once"] = True
            raise credential_store.CredentialError("write failed")
        state[target] = secret

    def delete(target):
        state[target] = ""

    with mock.patch.object(credential_store, "read_target",
                           side_effect=lambda target: state[target]), \
         mock.patch.object(credential_store, "write_target", side_effect=write), \
         mock.patch.object(credential_store, "delete_target", side_effect=delete):
        with pytest.raises(credential_store.CredentialError):
            credential_store.write_all(["new-primary", "new-backup"])
    assert state == before


def test_write_all_rejects_more_than_five_keys():
    with pytest.raises(credential_store.CredentialError):
        credential_store.write_all([str(index) for index in range(6)])
