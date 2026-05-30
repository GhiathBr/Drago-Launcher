import os
import json
import zipfile
import shutil
import tempfile
import requests
from pathlib import Path


def import_mrpack(mrpack_path: str, instance_path: str, progress_callback=None) -> tuple[bool, str]:
    try:
        if not os.path.exists(mrpack_path):
            return False, "File not found"

        instance_dir = Path(instance_path)
        instance_dir.mkdir(parents=True, exist_ok=True)

        def notify(msg, pct=None):
            if progress_callback:
                progress_callback(msg, pct)

        notify("Reading modpack...", 0.0)

        with zipfile.ZipFile(mrpack_path, "r") as zf:
            if "modrinth.index.json" not in zf.namelist():
                return False, "Invalid .mrpack: missing modrinth.index.json"

            index_data = json.loads(zf.read("modrinth.index.json"))

            notify(f"Modpack: {index_data.get('name', 'Unknown')}", 0.1)

            mods_dir = instance_dir / "mods"
            mods_dir.mkdir(exist_ok=True)

            overrides_path = index_data.get("overrides", "overrides")
            has_overrides = any(f.startswith(overrides_path + "/") for f in zf.namelist())

            notify("Extracting files...", 0.2)

            if has_overrides:
                for member in zf.namelist():
                    if member.startswith(overrides_path + "/") and not member.endswith("/"):
                        rel_path = os.path.relpath(member, overrides_path)
                        target = instance_dir / rel_path
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(member) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)

            files = index_data.get("files", [])
            total = len(files)

            notify(f"Downloading {total} mods...", 0.3)

            headers = {"User-Agent": "DragoLauncher/2.0"}
            success_count = 0
            fail_count = 0

            for i, file_entry in enumerate(files):
                downloads = file_entry.get("downloads", [])
                if not downloads:
                    fail_count += 1
                    continue

                file_path = file_entry.get("path", f"mods/{file_entry.get('fileName', 'unknown.jar')}")
                env_support = file_entry.get("env", {})

                if env_support.get("client") == "unsupported":
                    continue

                target_file = instance_dir / file_path
                target_file.parent.mkdir(parents=True, exist_ok=True)

                downloaded = False
                for url in downloads:
                    try:
                        resp = requests.get(url, headers=headers, timeout=30)
                        if resp.status_code == 200:
                            with open(target_file, "wb") as f:
                                f.write(resp.content)
                            downloaded = True
                            success_count += 1
                            break
                    except Exception:
                        continue

                if not downloaded:
                    fail_count += 1

                pct = 0.3 + (0.6 * (i + 1) / total)
                notify(f"Downloaded {i+1}/{total} files...", pct)

            notify("Creating instance metadata...", 0.9)

            metadata = {
                "name": index_data.get("name", "Imported Modpack"),
                "version": index_data.get("versionId", "unknown"),
                "summary": index_data.get("summary", ""),
                "mc_version": _get_mc_version_from_index(index_data),
                "loader": _get_loader_from_index(index_data),
                "mod_count": success_count,
                "fail_count": fail_count,
            }

            with open(instance_dir / "instance.json", "w") as f:
                json.dump(metadata, f, indent=4)

            notify(f"Done! {success_count} mods installed, {fail_count} failed", 1.0)

            return True, metadata.get("name", "Imported Modpack")

    except zipfile.BadZipFile:
        return False, "Invalid zip file"
    except Exception as e:
        return False, f"Import error: {e}"


def _get_mc_version_from_index(index: dict) -> str:
    deps = index.get("dependencies", {})
    return deps.get("minecraft", "unknown")


def _get_loader_from_index(index: dict) -> str:
    deps = index.get("dependencies", {})
    if "fabric-loader" in deps:
        return "fabric"
    if "quilt-loader" in deps:
        return "quilt"
    if "forge" in deps:
        return "forge"
    if "neoforge" in deps:
        return "neoforge"
    return "vanilla"


def export_mrpack(instance_path: str, output_path: str, progress_callback=None) -> tuple[bool, str]:
    try:
        instance_dir = Path(instance_path)
        if not instance_dir.exists():
            return False, "Instance not found"

        def notify(msg, pct=None):
            if progress_callback:
                progress_callback(msg, pct)

        notify("Building modpack index...", 0.1)

        metadata_file = instance_dir / "instance.json"
        if metadata_file.exists():
            metadata = json.loads(metadata_file.read_text())
        else:
            metadata = {"name": instance_dir.name, "version": "1.0"}

        mods_dir = instance_dir / "mods"
        mod_files = []
        if mods_dir.exists():
            for f in mods_dir.iterdir():
                if f.suffix == ".jar":
                    mod_files.append(f)

        index = {
            "formatVersion": 1,
            "game": "minecraft",
            "versionId": metadata.get("version", "1.0"),
            "name": metadata.get("name", instance_dir.name),
            "summary": metadata.get("summary", ""),
            "files": [],
            "dependencies": {
                "minecraft": metadata.get("mc_version", "1.20.1"),
            },
            "overrides": "overrides",
        }

        loader = metadata.get("loader", "vanilla")
        if loader == "fabric":
            index["dependencies"]["fabric-loader"] = "*"
        elif loader == "quilt":
            index["dependencies"]["quilt-loader"] = "*"
        elif loader == "forge":
            index["dependencies"]["forge"] = "*"
        elif loader == "neoforge":
            index["dependencies"]["neoforge"] = "*"

        notify(f"Adding {len(mod_files)} mods...", 0.3)

        headers = {"User-Agent": "DragoLauncher/2.0"}
        for i, mod_file in enumerate(mod_files):
            index["files"].append({
                "path": f"mods/{mod_file.name}",
                "downloads": [],
                "fileSize": mod_file.stat().st_size,
            })
            pct = 0.3 + (0.2 * (i + 1) / max(len(mod_files), 1))
            notify(f"Scanning mods {i+1}/{len(mod_files)}...", pct)

        notify("Creating archive...", 0.6)
        import tempfile
        import uuid

        temp_dir = Path(tempfile.gettempdir()) / f"mrpack_{uuid.uuid4().hex}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        with open(temp_dir / "modrinth.index.json", "w") as f:
            json.dump(index, f, indent=4)

        overrides_dir = temp_dir / "overrides"
        overrides_dir.mkdir(exist_ok=True)

        for item in ["mods", "config", "scripts", "resourcepacks", "shaderpacks"]:
            src = instance_dir / item
            if src.exists():
                dst = overrides_dir / item
                shutil.copytree(src, dst, dirs_exist_ok=True)

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in temp_dir.rglob("*"):
                if f.is_file():
                    arcname = str(f.relative_to(temp_dir))
                    zf.write(f, arcname)

        shutil.rmtree(temp_dir, ignore_errors=True)

        notify("Export complete!", 1.0)
        return True, output_path

    except Exception as e:
        return False, f"Export error: {e}"
