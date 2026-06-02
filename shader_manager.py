import os
import requests
import shutil
import re
import zipfile
import tempfile
from pathlib import Path
from io import BytesIO


COMPLEMENTARY_URL = "https://api.github.com/repos/ComplementaryShaders/ComplementaryShaders_V4/releases/latest"
BSL_URL = "https://api.github.com/repos/PeopleWhoCanDoThings/BSL-Shaders/releases/latest"
SILDURS_URL = "https://api.github.com/repos/sildurshaders/sildurs-shaders/releases/latest"


KNOWN_SHADERS = [
    {
        "name": "Complementary Shaders v4",
        "author": "ComplementaryShaders",
        "url": COMPLEMENTARY_URL,
        "type": "github",
    },
    {
        "name": "BSL Shaders",
        "author": "capttatsu",
        "url": BSL_URL,
        "type": "github",
    },
    {
        "name": "Sildur's Shaders",
        "author": "sildurshaders",
        "url": "https://sildurs-shaders.github.io/downloads/",
        "type": "web",
    },
    {
        "name": "Kappa Shader",
        "author": "RRe36",
        "url": "https://api.github.com/repos/RRe36/Kappa-Shader/releases/latest",
        "type": "github",
    },
    {
        "name": "Solas Shader",
        "author": "RRe36",
        "url": "https://api.github.com/repos/RRe36/Solas-Shader/releases/latest",
        "type": "github",
    },
    {
        "name": "MakeUp-UltraFast",
        "author": "Sildur",
        "url": "https://api.github.com/repos/sildurshaders/makeup-ultrafast/releases/latest",
        "type": "github",
    },
    {
        "name": "Photon Shader",
        "author": "SixthSurge",
        "url": "https://api.github.com/repos/SixthSurge/Photon/releases/latest",
        "type": "github",
    },
    {
        "name": "Nostalgia Shader",
        "author": "dev-dwarf",
        "url": "https://api.github.com/repos/dev-dwarf/Nostalgia-Shader/releases/latest",
        "type": "github",
    },
]


def get_shader_version_info(shader: dict) -> dict | None:
    try:
        if shader["type"] == "github":
            resp = requests.get(shader["url"], headers={"User-Agent": "DragoLauncher/2.0"}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                assets = data.get("assets", [])
                zip_assets = [a for a in assets if a["name"].endswith(".zip")]
                return {
                    "version": data.get("tag_name", "latest"),
                    "name": data.get("name", shader["name"]),
                    "download_url": zip_assets[0]["browser_download_url"] if zip_assets else None,
                    "size": zip_assets[0].get("size", 0) if zip_assets else 0,
                }
        elif shader["type"] == "web":
            return {
                "version": "latest",
                "name": shader["name"],
                "download_url": shader["url"],
                "size": 0,
            }
    except Exception as e:
        print(f"Error fetching shader info: {e}")
    return None


def install_shader(download_url: str, shader_name: str, shaderpacks_dir: str, progress_cb=None) -> tuple[bool, str]:
    try:
        os.makedirs(shaderpacks_dir, exist_ok=True)

        if progress_cb:
            progress_cb(0.1, f"Downloading {shader_name}...")

        resp = requests.get(download_url, stream=True, timeout=60)
        if resp.status_code != 200:
            return False, f"Download failed (HTTP {resp.status_code})"

        content_type = resp.headers.get("content-type", "")
        content_disposition = resp.headers.get("content-disposition", "")

        filename = shader_name
        if "filename=" in content_disposition:
            filename = content_disposition.split("filename=")[-1].strip('" ')
        if not filename.endswith(".zip"):
            filename = re.sub(r'[^\w\-_. ]', "_", shader_name) + ".zip"

        target_path = os.path.join(shaderpacks_dir, filename)

        total_size = int(resp.headers.get("content-length", 0))
        downloaded = 0

        with open(target_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0 and progress_cb:
                        progress_cb(0.1 + 0.7 * downloaded / total_size, f"Downloading {shader_name}...")

        if progress_cb:
            progress_cb(1.0, f"Installed {shader_name}!")

        return True, f"Installed {os.path.basename(target_path)}"

    except Exception as e:
        return False, str(e)


def list_installed_shaders(shaderpacks_dir: str) -> list[str]:
    dir_path = Path(shaderpacks_dir)
    if not dir_path.exists():
        return []
    return sorted([
        f.name for f in dir_path.iterdir()
        if f.suffix == ".zip" or f.is_dir()
    ])
