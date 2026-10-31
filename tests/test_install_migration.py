"""Installer contract: setup layout, migration cleanup, data preservation.

The .iss is the spec. These tests pin what the user was promised:
same-folder overwrite (fixed inner name), shortcuts managed by setup,
old portable leftovers cleaned, and user data (recordings, meetings,
downloaded models) never touched by install or uninstall.
"""

import os
import re
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
ISS = ROOT / "installer" / "wordarc.iss"


def iss_text():
    return ISS.read_text(encoding="utf-8-sig")


class IssLayoutTests(unittest.TestCase):
    def test_iss_exists_with_env_version_and_admin_program_files(self):
        body = iss_text()
        self.assertIn('#define AppVersion GetEnv("WORDARC_VERSION")', body)
        self.assertIn('#define AppVersionNum GetEnv("WORDARC_VERSION_NUM")', body)
        self.assertNotRegex(body, r"AppVersion=\d+\.\d+\.\d+",
                            "version must come from the environment, not hardcoded")
        self.assertIn("PrivilegesRequired=admin", body)
        self.assertIn("DefaultDirName={autopf}\\WordArc", body)
        self.assertIn("ArchitecturesAllowed=x64compatible", body)
        self.assertIn("OutputBaseFilename=WordArc-{#AppVersion}", body)

    def test_app_id_is_a_real_guid(self):
        body = iss_text()
        match = re.search(r"AppId=\{\{([0-9A-Fa-f-]{36})\}\}", body)
        self.assertIsNotNone(match, "AppId must be a GUID")
        self.assertNotIn("00000000", match.group(1),
                         "placeholder GUID must be replaced")

    def test_single_inner_exe_no_version_in_name(self):
        body = iss_text()
        self.assertIn('Source: "..\\dist\\inner\\WordArc.exe"', body)
        self.assertIn('DestDir: "{app}"', body)
        self.assertNotIn("WordArc-{#AppVersion}.exe\"; DestDir", body)

    def test_shortcuts_come_from_setup(self):
        body = iss_text()
        self.assertIn('Name: "{group}\\WordArc"', body)
        self.assertIn('Name: "{autodesktop}\\WordArc"', body)
        self.assertIn('Filename: "{app}\\WordArc.exe"', body)

    def test_setup_carries_the_product_icon(self):
        body = iss_text()
        self.assertIn("SetupIconFile=", body)
        ico = ROOT / "assets" / "brand" / "wordarc.ico"
        self.assertTrue(ico.is_file(), "product icon missing")

    def test_setup_restarts_the_app_unelevated(self):
        body = iss_text()
        run_section = body.split("[Run]", 1)[1]
        self.assertIn("runasoriginaluser", run_section)


class IssMigrationTests(unittest.TestCase):
    def test_old_portable_is_cleaned(self):
        body = iss_text()
        self.assertIn("CleanOldPortable", body)
        self.assertIn("WordArc-*.exe", body)
        self.assertIn("WordArc-*.bat", body)
        self.assertIn("Programs\\WordArc", body)

    def test_legacy_verbatim_launch_points_are_removed(self):
        body = iss_text()
        self.assertIn("Verbatim.lnk", body)
        self.assertIn("'Verbatim'", body)

    def test_user_data_is_never_deleted(self):
        body = iss_text()
        self.assertNotIn("DelTree", body)
        for protected in ("recordings", "meetings", "models",
                          "config.json", "history.jsonl"):
            for line in body.splitlines():
                stripped = line.strip()
                if stripped.startswith(";"):
                    continue
                self.assertNotIn(
                    protected, stripped,
                    f"installer must not reference user data: {stripped}")


class IssLanguageTests(unittest.TestCase):
    def test_setup_asks_language_with_all_13_codes(self):
        import i18n
        body = iss_text()
        section = body.split("[Languages]", 1)[1].split("[", 1)[0]
        names = re.findall(r'Name:\s*"([^"]+)"', section)
        # Inno names cannot contain hyphens, so pt-BR/zh-CN ship as ptBR/zhCN
        # and the app maps them back (see _setup_language_arg).
        safe = [code.replace("-", "") for code, _label in i18n.LANGUAGES]
        self.assertEqual(names, safe)
        for name in names:
            self.assertRegex(name, r"^[A-Za-z_][A-Za-z0-9_]*$")

    def test_task_descriptions_are_translated_per_language(self):
        import i18n
        body = iss_text()
        section = body.split("[CustomMessages]", 1)[1].split("[", 1)[0]
        for code, _label in i18n.LANGUAGES:
            safe = code.replace("-", "")
            self.assertIn(f"{safe}.DesktopIcon=", section)
            self.assertIn(f"{safe}.AutoStart=", section)
        tasks = body.split("[Tasks]", 1)[1].split("[", 1)[0]
        self.assertIn("{cm:DesktopIcon}", tasks)
        self.assertIn("{cm:AutoStart}", tasks)

    def test_setup_language_reaches_first_launch(self):
        body = iss_text()
        run_section = body.split("[Run]", 1)[1].split("[Code]", 1)[0]
        self.assertIn("--setup-language {language}", run_section)


class UpdateFlowTests(unittest.TestCase):
    def test_setup_flow_replaces_the_swap_flow(self):
        import update
        self.assertTrue(hasattr(update, "setup_temp_path"))
        self.assertTrue(hasattr(update, "spawn_setup"))
        self.assertFalse(hasattr(update, "spawn_swap"),
                        "swap batch flow is retired")
        self.assertFalse(hasattr(update, "install_path"),
                        "versioned side-by-side layout is retired")


if __name__ == "__main__":
    unittest.main()
