# -*- coding: utf-8 -*-
"""Portable network update checker for the standalone executable."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
from urllib.parse import urlparse
import urllib.error
import urllib.request


APP_VERSION = "1.1.3"
MANIFEST_URL_FILE = "update_manifest_url.txt"
DEFAULT_UPDATE_SOURCE = "https://api.github.com/repos/kanzakideath/Automatic-design-drawing-converter/releases/latest"
GITHUB_REPO_RE = re.compile(r"^https://github\.com/([^/]+)/([^/#?]+?)(?:\.git)?/?(?:[#?].*)?$", re.I)


@dataclass
class UpdateInfo:
    version: str
    url: str
    notes: str = ""
    sha256: str = ""
    mandatory: bool = False


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def data_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "data"
    return Path(__file__).resolve().parent / "data"


def current_executable() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return Path(__file__).resolve()


def read_manifest_url() -> str:
    env = os.environ.get("SMC_UPDATE_MANIFEST_URL", "").strip()
    if env:
        return env
    candidates = [
        app_dir() / MANIFEST_URL_FILE,
        app_dir() / "data" / MANIFEST_URL_FILE,
        data_dir() / MANIFEST_URL_FILE,
    ]
    for path in candidates:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line
    return DEFAULT_UPDATE_SOURCE


def _normalise_source_url(url: str) -> str:
    match = GITHUB_REPO_RE.match(url.strip())
    if not match:
        return url.strip()
    owner, repo = match.group(1), match.group(2)
    return "https://api.github.com/repos/%s/%s/releases/latest" % (owner, repo)


def _clean_version(value: str) -> str:
    value = value.strip()
    if value.lower().startswith("release-"):
        value = value[8:]
    if value.lower().startswith("version-"):
        value = value[8:]
    if value.lower().startswith("v") and len(value) > 1 and value[1].isdigit():
        value = value[1:]
    return value


def _version_key(value: str) -> tuple:
    value = _clean_version(value)
    parts = re.findall(r"\d+|[a-zA-Z]+", value)
    key = []
    for part in parts:
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part.lower()))
    return tuple(key)


def is_newer(remote: str, current: str = APP_VERSION) -> bool:
    return _version_key(remote) > _version_key(current)


def _github_release_to_update(data: dict) -> UpdateInfo | None:
    tag = str(data.get("tag_name") or data.get("name") or "").strip()
    version = _clean_version(tag)
    assets = data.get("assets") or []
    candidates = []
    for asset in assets:
        name = str(asset.get("name", ""))
        download_url = str(asset.get("browser_download_url", ""))
        if not download_url or not name.lower().endswith(".exe"):
            continue
        score = 0
        lowered = name.lower()
        if "設計図素材変換ツール" in name:
            score += 50
        if "schematic" in lowered or "converter" in lowered:
            score += 25
        if "setup" in lowered or "installer" in lowered:
            score -= 20
        digest = str(asset.get("digest") or "").strip().lower()
        sha256 = digest[7:] if digest.startswith("sha256:") else ""
        candidates.append((score, name, download_url, sha256))
    if not version or not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    _score, _name, download_url, sha256 = candidates[0]
    notes = str(data.get("body") or "").strip()
    return UpdateInfo(
        version=version,
        url=download_url,
        notes=notes,
        sha256=sha256,
        mandatory=False,
    )


def fetch_manifest(timeout: int = 8) -> UpdateInfo | None:
    url = _normalise_source_url(read_manifest_url())
    if not url:
        return None
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "SchematicMaterialConverter/%s" % APP_VERSION,
            "Accept": "application/vnd.github+json, application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8-sig"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404 and "api.github.com/repos/" in url and "/releases/latest" in url:
            return None
        raise
    if isinstance(data, dict) and ("tag_name" in data or "assets" in data):
        return _github_release_to_update(data)
    version = str(data.get("version", "")).strip()
    download_url = str(data.get("url") or data.get("download_url") or "").strip()
    if not version or not download_url:
        return None
    return UpdateInfo(
        version=version,
        url=download_url,
        notes=str(data.get("notes", "")).strip(),
        sha256=str(data.get("sha256", "")).strip().lower(),
        mandatory=bool(data.get("mandatory", False)),
    )


def check_for_update(timeout: int = 8) -> UpdateInfo | None:
    info = fetch_manifest(timeout=timeout)
    if info and is_newer(info.version):
        return info
    return None


def check_for_update_async(on_result, on_error=None) -> None:
    def worker() -> None:
        try:
            info = check_for_update()
        except Exception as exc:
            if on_error:
                on_error(exc)
            return
        on_result(info)

    threading.Thread(target=worker, daemon=True).start()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_update(info: UpdateInfo, progress=None) -> Path:
    suffix = Path(urlparse(info.url).path).suffix or ".exe"
    fd, temp_name = tempfile.mkstemp(prefix="smc-update-", suffix=suffix)
    os.close(fd)
    out = Path(temp_name)
    req = urllib.request.Request(info.url, headers={"User-Agent": "SchematicMaterialConverter/%s" % APP_VERSION})
    with urllib.request.urlopen(req, timeout=30) as response, out.open("wb") as handle:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = response.read(1024 * 512)
            if not chunk:
                break
            handle.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(done / total)
    if info.sha256 and _sha256(out).lower() != info.sha256:
        try:
            out.unlink()
        except OSError:
            pass
        raise ValueError("更新ファイルのSHA256が一致しません。")
    return out


def schedule_replace_and_restart(new_exe: Path) -> None:
    current = current_executable()
    if current.suffix.lower() != ".exe":
        raise RuntimeError("開発実行中は自動置き換えできません。")
    script = Path(tempfile.gettempdir()) / ("smc-apply-update-%s.ps1" % os.getpid())
    ps = f"""
$ErrorActionPreference = "Stop"
$PidToWait = {os.getpid()}
$NewExe = "{str(new_exe)}"
$CurrentExe = "{str(current)}"
try {{
  Wait-Process -Id $PidToWait -Timeout 60 -ErrorAction SilentlyContinue
}} catch {{}}
Start-Sleep -Milliseconds 700
Copy-Item -LiteralPath $NewExe -Destination $CurrentExe -Force
Remove-Item -LiteralPath $NewExe -Force -ErrorAction SilentlyContinue
Start-Process -FilePath $CurrentExe -WorkingDirectory (Split-Path -Parent $CurrentExe)
Start-Sleep -Milliseconds 500
Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue
"""
    script.write_text(ps, encoding="utf-8-sig")
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
