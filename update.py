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
import os
import re
import ssl
import urllib.error
import urllib.request
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path

from brand import BRAND
from i18n import t

RELEASE_REPO = "zeitgeist-c/WordArc-Releases"
API_LATEST = f"https://api.github.com/repos/{RELEASE_REPO}/releases/latest"
USER_AGENT = f"{BRAND.name}/{BRAND.version}"
log = logging.getLogger("wordarc.update")


@lru_cache(maxsize=1)
def _https_context():
    """Use the shipped CA roots; retain them in memory after bundle cleanup.

    Loading Windows' default certificate stores can itself fail with X509/BIO
    in the frozen app, before urlopen has made any network request.
    Explicit CA data avoids that path while retaining hostname/cert checks.
    """
    import certifi
    return ssl.create_default_context(cadata=certifi.contents())


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
        with urllib.request.urlopen(request, timeout=20, context=_https_context()) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        log.warning("update check failed: %s", type(exc).__name__)
        raise UpdateError("Update server could not be reached.") from exc
    try:
        return parse_release(payload)
    except (AttributeError, TypeError, ValueError) as exc:
        raise UpdateError("The update server returned an invalid response.") from exc


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
        with urllib.request.urlopen(request, timeout=60, context=_https_context()) as response:
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


def setup_temp_path(version: str) -> Path:
    """Where the downloaded setup installer waits before it is launched."""
    import config
    return config.DATA_DIR / "updates" / "downloads" / f"{BRAND.name}-{version}.exe"


def spawn_setup(setup_exe: Path, *, version: str, sha256: str, timeout=110,
                old_exe=None, old_pid=None, helper_dir=None) -> Path:
    """Wait off the GUI thread for installer readiness, never just ShellExecute success."""
    import json
    import shutil
    import subprocess
    import sys
    import time
    import uuid
    import config
    from brand import resource_path
    import update_protocol as protocol
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise UpdateError("Invalid update version")
    if not sha256 or protocol.digest(setup_exe) != sha256:
        raise UpdateError("The checksum of the downloaded file does not match.")
    folder = config.DATA_DIR / "updates" / "sessions" / uuid.uuid4().hex
    folder.mkdir(parents=True)
    current = Path(old_exe or sys.executable).resolve()
    previous = folder / "previous" / "WordArc.exe"
    previous.parent.mkdir()
    shutil.copy2(current, previous)
    helpers = Path(helper_dir) if helper_dir is not None else resource_path("helpers")
    source = helpers / "WordArcUpdate.exe"
    manifest = json.loads((helpers / "manifest.json").read_text(encoding="utf-8"))
    if protocol.digest(source) != manifest["sha256"]:
        raise UpdateError("The update supervisor is damaged. Reinstall WordArc.")
    helper = folder / "WordArcUpdate.exe"
    shutil.copy2(source, helper)
    owned = [dict(path=str(current), sha256=protocol.digest(current))]
    # The installer's own small uninstall files share the app directory. They
    # are removed only if their exact pre-update bytes remain unchanged.
    for name in ("unins000.exe", "unins000.dat"):
        path = current.parent / name
        if path.is_file():
            owned.append(dict(path=str(path), sha256=protocol.digest(path)))
    job = dict(schema=1, id=folder.name, version=version,
               setup=str(Path(setup_exe).resolve()), sha256=sha256,
               old_pid=old_pid or os.getpid(), old_exe=str(current), old_sha256=owned[0]["sha256"],
               new_exe=str(protocol.install_directory() / "WordArc.exe"), old_files=owned)
    (folder / "job.json").write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    process = subprocess.Popen([str(helper), "--job", str(folder / "job.json")],
                               env=protocol.clean_environment(), close_fds=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = protocol.read_state(folder)
        if state.get("stage") == "ready":
            log.info("installer readiness confirmed: %s", folder)
            return folder
        if state.get("stage") == "failed":
            raise UpdateError(f"{state.get('error', 'Setup failed')}\n{folder / 'setup.log'}")
        if process.poll() is not None:
            raise UpdateError(f"Update supervisor exited before readiness.\n{folder / 'setup.log'}")
        time.sleep(0.1)
    (folder / "cancel.requested").touch()
    raise UpdateError(f"Setup did not become ready; the current app remains open.\n{folder / 'setup.log'}")


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
