import os
import json
import shutil
import zipfile
import tempfile
import uuid
from pathlib import Path
from datetime import datetime, timedelta


BACKUP_DIR_NAME = "backups"


class BackupManager:
    def __init__(self, instances_dir: str):
        self.instances_dir = Path(instances_dir)
        self.backup_dir = self.instances_dir.parent / BACKUP_DIR_NAME
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.backup_dir / "backup_index.json"
        self.index = self._load_index()

    def _load_index(self) -> dict:
        if self.index_file.exists():
            try:
                return json.loads(self.index_file.read_text())
            except Exception:
                pass
        return {"backups": []}

    def _save_index(self):
        self.index_file.write_text(json.dumps(self.index, indent=4))

    def create_backup(self, instance_id: str, name: str = None, backup_type: str = "full") -> str | None:
        instance_path = self.instances_dir / instance_id
        if not instance_path.exists():
            return None

        backup_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        backup_name = name or f"Backup_{timestamp[:10]}"

        backup_path = self.backup_dir / backup_id
        backup_path.mkdir(parents=True, exist_ok=True)

        try:
            metadata_path = instance_path / "instance.json"
            metadata = {}
            if metadata_path.exists():
                metadata = json.loads(metadata_path.read_text())

            if backup_type == "worlds":
                saves_src = instance_path / "saves"
                if saves_src.exists():
                    shutil.copytree(saves_src, backup_path / "saves", dirs_exist_ok=True)
            elif backup_type == "config":
                config_src = instance_path / "config"
                if config_src.exists():
                    shutil.copytree(config_src, backup_path / "config", dirs_exist_ok=True)
            elif backup_type == "mods":
                mods_src = instance_path / "mods"
                if mods_src.exists():
                    shutil.copytree(mods_src, backup_path / "mods", dirs_exist_ok=True)
            else:
                shutil.copytree(instance_path, backup_path, dirs_exist_ok=True)

            backup_info = {
                "id": backup_id,
                "instance_id": instance_id,
                "name": backup_name,
                "type": backup_type,
                "created": timestamp,
                "size": self._get_dir_size(backup_path),
                "metadata": metadata,
            }

            self.index["backups"].append(backup_info)
            self._save_index()

            return backup_id

        except Exception as e:
            print(f"Backup creation failed: {e}")
            if backup_path.exists():
                shutil.rmtree(backup_path)
            return None

    def restore_backup(self, backup_id: str, instance_id: str) -> bool:
        backup_info = self._get_backup_info(backup_id)
        if not backup_info:
            return False

        backup_path = self.backup_dir / backup_id
        if not backup_path.exists():
            return False

        instance_path = self.instances_dir / instance_id

        try:
            backup_type = backup_info.get("type", "full")

            if backup_type == "worlds":
                target = instance_path / "saves"
                if target.exists():
                    shutil.rmtree(target)
                if (backup_path / "saves").exists():
                    shutil.copytree(backup_path / "saves", target)
            elif backup_type == "config":
                target = instance_path / "config"
                if target.exists():
                    shutil.rmtree(target)
                if (backup_path / "config").exists():
                    shutil.copytree(backup_path / "config", target)
            elif backup_type == "mods":
                target = instance_path / "mods"
                if target.exists():
                    shutil.rmtree(target)
                if (backup_path / "mods").exists():
                    shutil.copytree(backup_path / "mods", target)
            else:
                for item in backup_path.iterdir():
                    if item.name in ["mods", "saves", "config", "resourcepacks", "shaderpacks"]:
                        target = instance_path / item.name
                        if target.exists():
                            shutil.rmtree(target)
                        shutil.copytree(item, target)

            return True

        except Exception as e:
            print(f"Restore failed: {e}")
            return False

    def delete_backup(self, backup_id: str) -> bool:
        backup_path = self.backup_dir / backup_id
        try:
            if backup_path.exists():
                shutil.rmtree(backup_path)
            self.index["backups"] = [b for b in self.index["backups"] if b["id"] != backup_id]
            self._save_index()
            return True
        except Exception as e:
            print(f"Backup deletion failed: {e}")
            return False

    def get_backups_for_instance(self, instance_id: str) -> list[dict]:
        return [b for b in self.index.get("backups", []) if b["instance_id"] == instance_id]

    def get_all_backups(self) -> list[dict]:
        return sorted(
            self.index.get("backups", []),
            key=lambda x: x.get("created", ""),
            reverse=True,
        )

    def cleanup_old_backups(self, max_backups: int = 10, max_days: int = 30):
        to_delete = []
        backups = self.get_all_backups()

        if len(backups) > max_backups:
            to_delete.extend(backups[max_backups:])

        cutoff = datetime.now() - timedelta(days=max_days)
        for b in backups:
            try:
                created = datetime.fromisoformat(b.get("created", ""))
                if created < cutoff:
                    if b not in to_delete:
                        to_delete.append(b)
            except Exception:
                pass

        for b in to_delete:
            self.delete_backup(b["id"])

    def get_backup_size(self, backup_id: str) -> int:
        backup_path = self.backup_dir / backup_id
        return self._get_dir_size(backup_path) if backup_path.exists() else 0

    def _get_backup_info(self, backup_id: str) -> dict | None:
        for b in self.index.get("backups", []):
            if b["id"] == backup_id:
                return b
        return None

    def _get_dir_size(self, path: Path) -> int:
        total = 0
        for f in path.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except Exception:
                    pass
        return total

    @staticmethod
    def format_size(size_bytes: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"

    def export_backup(self, backup_id: str, output_path: str) -> bool:
        backup_path = self.backup_dir / backup_id
        if not backup_path.exists():
            return False
        try:
            shutil.make_archive(
                output_path.replace(".zip", ""),
                "zip",
                backup_path,
            )
            return True
        except Exception as e:
            print(f"Backup export failed: {e}")
            return False

    def auto_backup_before_launch(self, instance_id: str) -> str | None:
        backup_id = self.create_backup(
            instance_id,
            name=f"Pre-launch {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            backup_type="full",
        )
        self.cleanup_old_backups(max_backups=20, max_days=14)
        return backup_id
