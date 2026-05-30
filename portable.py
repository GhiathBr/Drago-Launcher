import os
import json
import shutil
from pathlib import Path


CONFIG_FILENAME = "drago_launcher_config.json"
PORTABLE_MARKER = ".portable_mode"
PORTABLE_DIRS = [
    "instances",
    "logs",
    "config",
    "CustomSkinLoader",
    "cache",
]


def is_portable() -> bool:
    marker = Path(PORTABLE_MARKER)
    if marker.exists():
        return True
    config = Path(CONFIG_FILENAME)
    if config.exists():
        try:
            data = json.loads(config.read_text())
            return data.get("portable_mode", False)
        except Exception:
            pass
    return False


def enable_portable_mode(launcher_dir: str) -> bool:
    launcher_path = Path(launcher_dir)
    appdata_minecraft = Path(os.path.expandvars(r"%APPDATA%\.minecraft"))
    appdata_drago = Path(os.path.expandvars(r"%APPDATA%\.drago_launcher"))

    try:
        for dir_name in PORTABLE_DIRS:
            target = launcher_path / dir_name
            target.mkdir(parents=True, exist_ok=True)

        if appdata_drago.exists() and appdata_drago != launcher_path / "data":
            dst = launcher_path / "data"
            dst.mkdir(parents=True, exist_ok=True)
            instances_src = appdata_drago / "instances"
            if instances_src.exists():
                dst_instances = dst / "instances"
                if not dst_instances.exists():
                    shutil.copytree(instances_src, dst_instances, dirs_exist_ok=True)

        marker = launcher_path / PORTABLE_MARKER
        marker.touch()

        config_path = launcher_path / CONFIG_FILENAME
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text())
                data["portable_mode"] = True
                config_path.write_text(json.dumps(data, indent=4))
            except Exception:
                pass

        return True
    except Exception as e:
        print(f"Portable mode enable failed: {e}")
        return False


def disable_portable_mode(launcher_dir: str) -> bool:
    try:
        marker = Path(launcher_dir) / PORTABLE_MARKER
        if marker.exists():
            marker.unlink()
        return True
    except Exception as e:
        print(f"Portable mode disable failed: {e}")
        return False


def get_data_dir(launcher_dir: str) -> str:
    if is_portable():
        portable_data = Path(launcher_dir) / "data"
        portable_data.mkdir(parents=True, exist_ok=True)
        return str(portable_data)
    appdata = Path(os.path.expandvars(r"%APPDATA%\.drago_launcher"))
    appdata.mkdir(parents=True, exist_ok=True)
    return str(appdata)


def get_minecraft_dir(launcher_dir: str) -> str:
    if is_portable():
        portable_mc = Path(launcher_dir) / ".minecraft"
        portable_mc.mkdir(parents=True, exist_ok=True)
        return str(portable_mc)
    mine_dir = Path(os.path.expandvars(r"%APPDATA%\.minecraft"))
    mine_dir.mkdir(parents=True, exist_ok=True)
    return str(mine_dir)


def migrate_to_portable(source_appdata: str, target_launcher: str) -> bool:
    source = Path(source_appdata)
    target = Path(target_launcher) / "data"
    try:
        if source.exists() and not target.exists():
            shutil.copytree(source, target, dirs_exist_ok=True)
        enable_portable_mode(target_launcher)
        return True
    except Exception as e:
        print(f"Migration failed: {e}")
        return False
