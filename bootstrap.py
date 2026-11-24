"""自嘲熊 Windows 启动器：内置初始代码，启动时自动从 GitHub 拉取最新版本。

    python bootstrap.py

打包成 exe 后，首次运行会把内置的 main.py / bearpet / assets 复制到用户目录，
之后每次启动检查仓库最新提交；有更新就下载 zipball 覆盖这些文件，再启动程序。
网络失败时静默使用本地已有版本，保证离线可用。
"""
from __future__ import annotations

import json
import os
import runpy
import shutil
import sys
import urllib.request
import zipfile

REPO = "XxTxXTxX/desktop-joke-bear"
BRANCH = "main"
API_URL = f"https://api.github.com/repos/{REPO}/commits/{BRANCH}"
# github.com/.../archive/... 会 302 到 codeload；部分网络下这个跳转会被重置。
# 直接访问 codeload，并按 commit sha 下载，保证拿到的代码和 API 返回的版本一致。
ZIP_URL = "https://codeload.github.com/{repo}/zip/{sha}"
APP_FILES = ("main.py", "bearpet", "assets")
SHA_FILE = ".commit_sha"
API_TIMEOUT = 8
ZIP_TIMEOUT = 60


def _pyinstaller_hints():
    """仅用于让 PyInstaller 静态分析到运行期才加载的依赖，永不被调用。

    main.py / bearpet 是以数据文件形式随 exe 分发、启动时从用户目录 runpy 加载的，
    PyInstaller 看不到它们内部的 import，因此必须在这里显式声明，否则打包后会缺
    ctypes / PIL 子模块等。
    """
    import ctypes
    import ctypes.wintypes
    from PIL import Image, ImageChops, ImageDraw, ImageDraw2, ImageEnhance
    from PIL import ImageFilter, ImageFont, ImageOps, ImageStat
    import bearpet.app
    import bearpet.winlayer
    import bearpet.winlayer_win
    import bearpet.editor
    import bearpet.editor_win
    import bearpet.chat_ui
    import bearpet.chat_ui_win
    import bearpet.paths
    import bearpet.sprite
    import bearpet.art
    import bearpet.brain
    import bearpet.chat
    import bearpet.food
    import bearpet.fx
    import bearpet.garment
    import bearpet.lines
    import bearpet.outfit
    import bearpet.pixelfig
    import bearpet.remind_ui
    import bearpet.reminder
    import bearpet.remote
    import bearpet.size
    import bearpet.wardrobe


def bundle_dir() -> str:
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def app_dir() -> str:
    root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(root, "DeskBear", "app")


def local_sha(directory: str) -> str:
    try:
        with open(os.path.join(directory, SHA_FILE), encoding="ascii") as f:
            return f.read().strip()
    except OSError:
        return ""


def save_sha(directory: str, sha: str) -> None:
    with open(os.path.join(directory, SHA_FILE), "w", encoding="ascii") as f:
        f.write(sha)


def copy_bundled_code(directory: str) -> None:
    source = bundle_dir()
    for name in APP_FILES:
        src = os.path.join(source, name)
        dst = os.path.join(directory, name)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        elif os.path.isfile(src):
            shutil.copy2(src, dst)


def fetch_latest_sha() -> str:
    request = urllib.request.Request(API_URL, headers={
        "User-Agent": "desk-bear-updater",
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(request, timeout=API_TIMEOUT) as response:
        data = json.load(response)
    return str(data.get("sha", ""))


def download_zip(path: str, sha: str) -> None:
    url = ZIP_URL.format(repo=REPO, sha=sha)
    request = urllib.request.Request(url, headers={
        "User-Agent": "desk-bear-updater",
    })
    with urllib.request.urlopen(request, timeout=ZIP_TIMEOUT) as response, \
            open(path, "wb") as target:
        shutil.copyfileobj(response, target)


def apply_zip(directory: str, zip_path: str) -> bool:
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        prefix = next((n.split("/")[0] for n in names
                       if n.endswith("/") and n.count("/") == 1), None)
        if prefix is None:
            prefix = next((n.split("/")[0] for n in names if "/" in n), None)
        if prefix is None:
            return False
        root = prefix + "/"
        selected = [n for n in names if n.startswith(root) and not n.endswith("/")
                    and any(n[len(root):] == f or n[len(root):].startswith(f + "/")
                            for f in APP_FILES)]
        if not selected:
            return False
        for name in selected:
            relative = name[len(root):]
            target = os.path.join(directory, *relative.split("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with archive.open(name) as source, open(target, "wb") as output:
                shutil.copyfileobj(source, output)
    return True


def log(directory: str, message: str) -> None:
    try:
        with open(os.path.join(directory, "update.log"), "a", encoding="utf-8") as f:
            f.write(f"{message}\n")
    except OSError:
        pass


def check_update(directory: str) -> None:
    if os.environ.get("BEAR_NO_UPDATE") == "1":
        return
    staging = os.path.join(directory, ".update")
    try:
        sha = fetch_latest_sha()
        if not sha or sha == local_sha(directory):
            return
        os.makedirs(staging, exist_ok=True)
        archive = os.path.join(staging, "source.zip")
        download_zip(archive, sha)
        if apply_zip(directory, archive):
            save_sha(directory, sha)
            log(directory, f"updated to {sha}")
        else:
            log(directory, "update failed: no app files in archive")
    except Exception as exc:
        log(directory, f"update failed: {exc}")
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main() -> None:
    directory = app_dir()
    os.makedirs(directory, exist_ok=True)
    if not os.path.isfile(os.path.join(directory, "main.py")):
        copy_bundled_code(directory)
    check_update(directory)
    sys.path.insert(0, directory)
    runpy.run_path(os.path.join(directory, "main.py"), run_name="__main__")


if __name__ == "__main__":
    main()
