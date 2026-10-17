"""Self-update over the public WordArc-Releases GitHub repository.

The source repository stays private; releases (EXE + BAT only) live in a
public repo so a portable single-file install can ask "what is the newest
version?" without shipping a token inside the exe. The GitHub API answers
unauthenticated for public repos, rate limited per IP — a once-a-day check
uses one request and stays far under the limit.

A release always supersedes every older one, so an install on 0.8.1 jumps
straight to 0.8.6: it downloads `releases/latest`, never the steps between.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from brand import BRAND
from i18n import t

RELEASE_REPO = "zeitgeist-c/WordArc-Releases"
API_LATEST = f"https://api.github.com/repos/{RELEASE_REPO}/releases/latest"
USER_AGENT = f"{BRAND.name}/{BRAND.version}"
log = logging.getLogger("wordarc.update")


class UpdateError(Exception):
    """Anything the user must hear about verbatim: network, shape, checksum."""


@dataclass
class UpdateInfo:
    version: str
    asset_name: str
    download_url: str
    sha256: str          # expected digest, "" when the release omits it
    size: int
    page_url: str


def parse_version(text: str) -> tuple:
    """'v0.8.10' / '0.8.10-beta' -> (0, 8, 10); non-numeric tails stop."""
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", str(text or ""))
    if not match:
        raise UpdateError(t("Version number not understood: {version}")
                          .format(version=repr(text)))
    return tuple(int(part) for part in match.groups())


def is_newer(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)


def parse_release(payload: dict, version_prefix: str = "v") -> UpdateInfo:
    """Pull the exe asset out of a /releases/latest payload."""
    tag = str(payload.get("tag_name") or "")
    version = tag[len(version_prefix):] if tag.startswith(version_prefix) else tag
    parse_version(version)  # reject tags we cannot compare against
    exe_name = f"{BRAND.name}-{version}.exe"
    for asset in payload.get("assets") or []:
        if asset.get("name") != exe_name:
            continue
        digest = str(asset.get("digest") or "")
        return UpdateInfo(
            version=version,
            asset_name=exe_name,
            download_url=str(asset.get("browser_download_url") or ""),
            sha256=digest.split(":", 1)[1] if ":" in digest else digest,
            size=int(asset.get("size") or 0),
            page_url=str(payload.get("html_url") or ""),
        )
    raise UpdateError(t("The newest release has no {asset} asset.")
                      .format(asset=exe_name))


def fetch_latest() -> UpdateInfo:
    request = urllib.request.Request(API_LATEST, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise UpdateError("Update server could not be reached.") from exc
    return parse_release(payload)


def check_for_update(current: str) -> UpdateInfo | None:
    info = fetch_latest()
    return info if is_newer(info.version, current) else None


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(info: UpdateInfo, dest: Path, progress=None, cancel=None) -> Path:
    """Stream the asset to dest; verify size and SHA256 before it is kept.

    A half-written or tampered file must never become the running program,
    so a failed verification — or a cancel request — deletes the file.
    `cancel` is a threading.Event the progress callback polls.
    """
    class Cancelled(Exception):
        pass

    request = urllib.request.Request(info.download_url,
                                     headers={"User-Agent": USER_AGENT})
    dest.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            total = int(response.headers.get("Content-Length") or info.size)
            with dest.open("wb") as out:
                try:
                    while True:
                        chunk = response.read(1024 * 256)
                        if not chunk:
                            break
                        out.write(chunk)
                        written += len(chunk)
                        if progress:
                            progress(written, total)
                        if cancel is not None and cancel.is_set():
                            raise Cancelled()
                except Cancelled:
                    pass
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        dest.unlink(missing_ok=True)
        raise UpdateError("The update download was interrupted.") from exc
    if cancel is not None and cancel.is_set():
        dest.unlink(missing_ok=True)
        raise UpdateError("cancelled")
    if info.size and written != info.size:
        dest.unlink(missing_ok=True)
        raise UpdateError("The download ended before the file was complete.")
    if info.sha256:
        actual = _sha256_of(dest)
        if actual.lower() != info.sha256.lower():
            dest.unlink(missing_ok=True)
            raise UpdateError("The checksum of the downloaded file does not match.")
    return dest


def install_path(current_exe: Path, version: str) -> Path:
    """The new exe lives next to the old one under its release name."""
    return current_exe.with_name(f"{BRAND.name}-{version}.exe")


def spawn_swap(old_pid: int, new_exe: Path, old_exe: Path | None = None) -> None:
    """Hand the running exe over to the fresh copy.

    Windows will not replace a running exe; the batch waits for this process
    to exit, boots the new exe the way a restart would, then deletes itself.
    When ``old_exe`` is given and differs from the new one, the batch also
    removes the superseded exe (plus its version BAT) so only the new
    version remains on disk.
    """
    lines = [
        "@echo off\r\n",
        ":wait\r\n",
        f'tasklist /FI "PID eq {old_pid}" 2>NUL | find " {old_pid} " >NUL\r\n',
        "if not errorlevel 1 (timeout /t 1 /nobreak >NUL & goto wait)\r\n",
        f'start "" "{new_exe}" --restarted\r\n',
    ]
    if old_exe is not None and Path(old_exe) != Path(new_exe):
        old_exe = Path(old_exe)
        lines.append(f'del "{old_exe}"\r\n')
        old_bat = old_exe.with_name(old_exe.stem + ".bat")
        if old_bat.name.startswith(BRAND.name + "-"):
            lines.append(f'del "{old_bat}"\r\n')
    lines.append('del "%~f0"\r\n')
    script = new_exe.with_name(f"{BRAND.slug}-swap.bat")
    script.write_text("".join(lines), encoding="ascii")
    # CREATE_NEW_CONSOLE alone: combining it with DETACHED_PROCESS makes
    # Popen fail with WinError 87, which used to leave the UI stuck at 100%.
    subprocess.Popen(["cmd", "/c", str(script)], close_fds=True,
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    log.info("swap armed: pid=%s new=%s", old_pid, new_exe)


def last_check_is_old(stamp: str, max_age_seconds: float = 24 * 3600) -> bool:
    """True when the stored ISO stamp is missing or older than the window."""
    if not stamp:
        return True
    try:
        import datetime
        when = datetime.datetime.fromisoformat(stamp)
    except ValueError:
        return True
    import datetime
    age = (datetime.datetime.now() - when.replace(tzinfo=None)).total_seconds()
    return age > max_age_seconds


def now_stamp() -> str:
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")
