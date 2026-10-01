"""One source of truth for the WordArc product identity."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys


@dataclass(frozen=True)
class BrandIdentity:
    name: str = "WordArc"
    version: str = "0.6.6"
    slug: str = "wordarc"
    executable: str = "wordarc.exe"
    data_directory: str = "WordArc"
    credential_target: str = "WordArc/GeminiApiKey"
    legacy_name: str = "Verbatim"
    legacy_slug: str = "verbatim"
    legacy_executable: str = "verbatim.exe"
    legacy_credential_target: str = "Verbatim/GeminiApiKey"

    def ipc_name(self, username: str) -> str:
        return f"{self.slug}-{username}"

    def legacy_ipc_name(self, username: str) -> str:
        return f"{self.legacy_slug}-{username}"


BRAND = BrandIdentity()


def set_windows_app_id() -> None:
    """Make source-mode launches group under WordArc instead of pythonw.exe."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            f"{BRAND.name}.{BRAND.slug}"
        )
    except (AttributeError, OSError):
        # The icon set on QApplication remains the fallback on older Windows.
        pass


def resource_path(*parts: str) -> Path:
    """Resolve project assets both from source and a PyInstaller bundle."""
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return root.joinpath(*parts)


def brand_asset(filename: str) -> Path:
    return resource_path("assets", "brand", filename)
