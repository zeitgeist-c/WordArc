from unittest import mock

import startup


def _key():
    key = mock.MagicMock()
    key.__enter__.return_value = key
    key.__exit__.return_value = False
    return key


def test_enabled_reads_wordarc_hkcu_value():
    key = _key()
    with mock.patch.object(startup.winreg, "OpenKey", return_value=key), \
         mock.patch.object(startup.winreg, "QueryValueEx",
                           return_value=('"C:\\WordArc\\wordarc.exe"', 1)):
        assert startup.is_enabled()


def test_missing_value_is_disabled():
    with mock.patch.object(startup.winreg, "OpenKey",
                           side_effect=FileNotFoundError):
        assert not startup.is_enabled()


def test_enable_and_disable_write_only_current_user_run_key():
    key = _key()
    with mock.patch.object(startup.winreg, "CreateKeyEx", return_value=key), \
         mock.patch.object(startup.winreg, "SetValueEx") as set_value, \
         mock.patch.object(startup.winreg, "DeleteValue") as delete_value:
        startup.set_enabled(True, '"C:\\WordArc\\wordarc.exe"')
        set_value.assert_called_once_with(
            key, "WordArc", 0, startup.winreg.REG_SZ,
            '"C:\\WordArc\\wordarc.exe"',
        )
        startup.set_enabled(False)
        delete_value.assert_called_once_with(key, "WordArc")


def test_launch_command_uses_background_mode():
    assert startup.launch_command().endswith(" background")


def test_existing_startup_entry_is_upgraded_without_enabling_missing_entry():
    key = _key()
    with mock.patch.object(startup.winreg, "OpenKey", return_value=key), \
         mock.patch.object(startup.winreg, "QueryValueEx",
                           return_value=('"C:\\WordArc\\wordarc.exe"', 1)), \
         mock.patch.object(startup, "launch_command",
                           return_value='"C:\\WordArc\\wordarc.exe" background'), \
         mock.patch.object(startup, "set_enabled") as set_enabled:
        assert startup.ensure_current_command()
    set_enabled.assert_called_once_with(
        True, '"C:\\WordArc\\wordarc.exe" background'
    )

    with mock.patch.object(startup.winreg, "OpenKey",
                           side_effect=FileNotFoundError), \
         mock.patch.object(startup, "set_enabled") as set_enabled:
        assert not startup.ensure_current_command()
    set_enabled.assert_not_called()
