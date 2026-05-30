import os
import json
import requests
import subprocess
import tempfile
import shutil
from pathlib import Path


LOADER_API = {
    "fabric": {
        "meta": "https://meta.fabricmc.net/v2/versions",
        "loader_list": "https://meta.fabricmc.net/v2/versions/loader/{mc_version}",
        "installer": "https://meta.fabricmc.net/v2/versions/loader/{mc_version}/{loader_version}/profile/zip",
    },
    "forge": {
        "meta": "https://files.minecraftforge.net/net/minecraftforge/forge",
        "promos": "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json",
        "installer": "https://maven.minecraftforge.net/net/minecraftforge/forge/{forge_version}/forge-{forge_version}-installer.jar",
    },
    "quilt": {
        "meta": "https://meta.quiltmc.org/v3/versions",
        "loader_list": "https://meta.quiltmc.org/v3/versions/loader/{mc_version}",
        "installer": "https://meta.quiltmc.org/v3/versions/loader/{mc_version}/{loader_version}/profile/zip",
    },
    "neoforge": {
        "meta": "https://api.neoforged.net/api/v2",
        "versions": "https://api.neoforged.net/api/v2/versions",
        "installer": "https://maven.neoforged.net/releases/net/neoforged/neoforge/{neoforge_version}/neoforge-{neoforge_version}-installer.jar",
    },
}


AVAILABLE_LOADERS = ["vanilla", "fabric", "forge", "quilt", "neoforge"]


def get_loader_versions(loader: str, mc_version: str) -> list[dict]:
    if loader == "fabric":
        return _get_fabric_versions(mc_version)
    elif loader == "forge":
        return _get_forge_versions(mc_version)
    elif loader == "quilt":
        return _get_quilt_versions(mc_version)
    elif loader == "neoforge":
        return _get_neoforge_versions(mc_version)
    return []


def _get_fabric_versions(mc_version: str) -> list[dict]:
    try:
        url = LOADER_API["fabric"]["loader_list"].format(mc_version=mc_version)
        resp = requests.get(url, headers={"User-Agent": "DragoLauncher/2.0"}, timeout=10)
        if resp.status_code != 200:
            return []
        data = resp.json()
        return [
            {
                "version": entry["loader"]["version"],
                "display": f"Fabric {entry['loader']['version']}",
                "stable": entry["loader"].get("stable", True),
            }
            for entry in data
        ]
    except Exception as e:
        print(f"Error fetching Fabric versions: {e}")
        return []


def _get_forge_versions(mc_version: str) -> list[dict]:
    try:
        url = LOADER_API["forge"]["promos"]
        resp = requests.get(url, headers={"User-Agent": "DragoLauncher/2.0"}, timeout=10)
        if resp.status_code != 200:
            return []
        data = resp.json()
        promos = data.get("promos", {})
        results = []
        for key, version in promos.items():
            if key.startswith(f"{mc_version}-"):
                loader_raw = key.split("-")[-1]
                forge_ver = version if isinstance(version, str) else str(version)
                results.append({
                    "version": forge_ver,
                    "display": f"Forge {forge_ver}",
                    "stable": "recommended" in key or loader_raw == "recommended",
                })
        return results
    except Exception as e:
        print(f"Error fetching Forge versions: {e}")
        return []


def _get_quilt_versions(mc_version: str) -> list[dict]:
    try:
        url = LOADER_API["quilt"]["loader_list"].format(mc_version=mc_version)
        resp = requests.get(url, headers={"User-Agent": "DragoLauncher/2.0"}, timeout=10)
        if resp.status_code != 200:
            return []
        data = resp.json()
        return [
            {
                "version": entry["loader"]["version"],
                "display": f"Quilt {entry['loader']['version']}",
                "stable": True,
            }
            for entry in data
        ]
    except Exception as e:
        print(f"Error fetching Quilt versions: {e}")
        return []


def _get_neoforge_versions(mc_version: str) -> list[dict]:
    try:
        url = f"{LOADER_API['neoforge']['versions']}/{mc_version}"
        resp = requests.get(url, headers={"User-Agent": "DragoLauncher/2.0"}, timeout=10)
        if resp.status_code != 200:
            return []
        data = resp.json()
        versions = data if isinstance(data, list) else data.get("versions", [])
        return [
            {
                "version": v.get("version", v),
                "display": f"NeoForge {v.get('version', v)}",
                "stable": v.get("recommended", False) if isinstance(v, dict) else False,
            }
            for v in versions
        ]
    except Exception as e:
        print(f"Error fetching NeoForge versions: {e}")
        return []


def install_loader(
    loader: str,
    mc_version: str,
    loader_version: str,
    minecraft_dir: str,
    progress_callback=None,
) -> tuple[bool, str]:
    if loader == "fabric":
        return _install_fabric(mc_version, minecraft_dir, progress_callback)
    elif loader == "forge":
        return _install_forge(mc_version, loader_version, minecraft_dir, progress_callback)
    elif loader == "quilt":
        return _install_quilt(mc_version, loader_version, minecraft_dir, progress_callback)
    elif loader == "neoforge":
        return _install_neoforge(mc_version, loader_version, minecraft_dir, progress_callback)
    return False, f"Unknown loader: {loader}"


def _notify(msg, progress=None, cb=None):
    if cb:
        cb(msg, progress)
    print(f"[LoaderInstaller] {msg}")


def _install_fabric(mc_version: str, minecraft_dir: str, cb=None) -> tuple[bool, str]:
    try:
        _notify(f"Installing Fabric for MC {mc_version}...", 0.1, cb)
        import minecraft_launcher_lib
        minecraft_launcher_lib.fabric.install_fabric(mc_version, minecraft_dir)
        _notify(f"Fabric {mc_version} installed!", 1.0, cb)
        return True, f"fabric-loader-{mc_version}"
    except Exception as e:
        _notify(f"Fabric install failed: {e}", None, cb)
        return False, str(e)


def _install_forge(mc_version: str, loader_version: str, minecraft_dir: str, cb=None) -> tuple[bool, str]:
    try:
        forge_version = f"{mc_version}-{loader_version}" if loader_version else mc_version
        _notify(f"Downloading Forge {forge_version}...", 0.1, cb)

        installer_url = LOADER_API["forge"]["installer"].format(forge_version=forge_version)
        jar_path = os.path.join(minecraft_dir, f"forge-{forge_version}-installer.jar")

        resp = requests.get(installer_url, stream=True, timeout=30)
        if resp.status_code != 200:
            return False, f"Forge download failed (HTTP {resp.status_code})"

        with open(jar_path, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)

        _notify("Running Forge installer (headless)...", 0.5, cb)

        java_path = _find_java()
        if not java_path:
            java_path = "java"

        result = subprocess.run(
            [java_path, "-jar", jar_path, "--installServer", minecraft_dir],
            capture_output=True, text=True, timeout=120,
            cwd=minecraft_dir,
        )

        if os.path.exists(jar_path):
            os.remove(jar_path)

        if result.returncode != 0:
            return False, f"Forge installer failed: {result.stderr[:200]}"

        version_id = f"{mc_version}-forge"
        _find_and_rename_forge_version(minecraft_dir, mc_version)
        _notify(f"Forge {forge_version} installed!", 1.0, cb)
        return True, version_id
    except subprocess.TimeoutExpired:
        return False, "Forge installer timed out"
    except Exception as e:
        return False, f"Forge install error: {e}"


def _find_and_rename_forge_version(minecraft_dir: str, mc_version: str):
    versions_dir = Path(minecraft_dir) / "versions"
    if not versions_dir.exists():
        return
    for vdir in versions_dir.iterdir():
        if vdir.is_dir() and mc_version in vdir.name and "forge" in vdir.name.lower():
            return
    for vdir in versions_dir.iterdir():
        if vdir.is_dir() and vdir.name.startswith(f"{mc_version}-"):
            json_path = vdir / f"{vdir.name}.json"
            if json_path.exists():
                try:
                    data = json.loads(json_path.read_text())
                    if "inheritsFrom" in data:
                        return
                except Exception:
                    pass


def _install_quilt(mc_version: str, loader_version: str, minecraft_dir: str, cb=None) -> tuple[bool, str]:
    try:
        _notify(f"Installing Quilt {loader_version} for MC {mc_version}...", 0.1, cb)
        import minecraft_launcher_lib
        minecraft_launcher_lib.quilt.install_quilt(mc_version, minecraft_dir, loader_version)
        _notify(f"Quilt {loader_version} installed!", 1.0, cb)
        return True, f"quilt-loader-{mc_version}"
    except Exception as e:
        return False, f"Quilt install failed: {e}"


def _install_neoforge(mc_version: str, loader_version: str, minecraft_dir: str, cb=None) -> tuple[bool, str]:
    try:
        nf_version = loader_version or mc_version
        _notify(f"Downloading NeoForge {nf_version}...", 0.1, cb)

        installer_url = LOADER_API["neoforge"]["installer"].format(neoforge_version=nf_version)
        jar_path = os.path.join(minecraft_dir, f"neoforge-{nf_version}-installer.jar")

        resp = requests.get(installer_url, stream=True, timeout=30)
        if resp.status_code != 200:
            return False, f"NeoForge download failed (HTTP {resp.status_code})"

        with open(jar_path, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)

        _notify("Running NeoForge installer (headless)...", 0.5, cb)

        java_path = _find_java()
        if not java_path:
            java_path = "java"

        result = subprocess.run(
            [java_path, "-jar", jar_path, "--install-server", minecraft_dir],
            capture_output=True, text=True, timeout=120,
            cwd=minecraft_dir,
        )

        if os.path.exists(jar_path):
            os.remove(jar_path)

        if result.returncode != 0:
            return False, f"NeoForge installer failed: {result.stderr[:200]}"

        _notify(f"NeoForge {nf_version} installed!", 1.0, cb)
        return True, f"neoforge-{mc_version}"
    except subprocess.TimeoutExpired:
        return False, "NeoForge installer timed out"
    except Exception as e:
        return False, f"NeoForge install error: {e}"


def _find_java() -> str | None:
    for candidate in [
        os.environ.get("JAVA_HOME", ""),
        os.environ.get("JAVA8_HOME", ""),
        os.environ.get("JAVA17_HOME", ""),
        os.environ.get("JAVA21_HOME", ""),
    ]:
        if candidate:
            exe = os.path.join(candidate, "bin", "java.exe")
            if os.path.exists(exe):
                return exe
    import shutil
    return shutil.which("java")


def get_installed_loader(minecraft_dir: str, version_id: str) -> str | None:
    version_json = Path(minecraft_dir) / "versions" / version_id / f"{version_id}.json"
    if not version_json.exists():
        return None
    try:
        data = json.loads(version_json.read_text())
        inherits = data.get("inheritsFrom", "")
        if "fabric" in version_id.lower():
            return "fabric"
        if "forge" in version_id.lower():
            return "forge"
        if "quilt" in version_id.lower():
            return "quilt"
        if "neoforge" in version_id.lower() or "neoforge" in inherits.lower():
            return "neoforge"
    except Exception:
        pass
    return None


def get_loader_display_name(version_id: str) -> str:
    version_json_path = None
    mine_dir = os.path.expandvars(r"%APPDATA%\.minecraft")
    candidate = Path(mine_dir) / "versions" / version_id / f"{version_id}.json"
    if candidate.exists():
        version_json_path = candidate

    if version_json_path:
        try:
            data = json.loads(version_json_path.read_text())
            mc_version = data.get("inheritsFrom", version_id)
            if "fabric" in version_id.lower():
                return f"Fabric {mc_version}"
            if "forge" in version_id.lower():
                return f"Forge {mc_version}"
            if "quilt" in version_id.lower():
                return f"Quilt {mc_version}"
            if "neoforge" in version_id.lower():
                return f"NeoForge {mc_version}"
        except Exception:
            pass
    return version_id
