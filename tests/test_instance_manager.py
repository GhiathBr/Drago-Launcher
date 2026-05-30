import os
import sys
import json
import tempfile
import shutil
import uuid
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from instance_manager import InstanceManager


def test_create_instance():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = InstanceManager(base_dir=tmp)
        instance_id = mgr.create_instance("Test Instance", "1.20.1", "fabric")
        assert instance_id is not None
        instance = mgr.get_instance(instance_id)
        assert instance is not None
        assert instance["name"] == "Test Instance"
        assert instance["version"] == "1.20.1"
        assert instance["loader"] == "fabric"
        assert instance["play_count"] == 0


def test_instance_persistence():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = InstanceManager(base_dir=tmp)
        instance_id = mgr.create_instance("Persistent", "1.19.4", "forge")
        del mgr
        mgr2 = InstanceManager(base_dir=tmp)
        assert instance_id in mgr2.get_all_instances()
        assert mgr2.get_instance(instance_id)["name"] == "Persistent"


def test_delete_instance():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = InstanceManager(base_dir=tmp)
        instance_id = mgr.create_instance("To Delete", "1.18.2")
        assert mgr.delete_instance(instance_id) is True
        assert mgr.get_instance(instance_id) is None


def test_duplicate_instance():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = InstanceManager(base_dir=tmp)
        orig_id = mgr.create_instance("Original", "1.20.1", "fabric")
        dup_id = mgr.duplicate_instance(orig_id, "Copy")
        assert dup_id is not None
        assert dup_id != orig_id
        assert mgr.get_instance(dup_id)["name"] == "Copy"
        assert mgr.get_instance(dup_id)["loader"] == "fabric"


def test_rename_instance():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = InstanceManager(base_dir=tmp)
        instance_id = mgr.create_instance("Old Name", "1.20.1")
        assert mgr.rename_instance(instance_id, "New Name") is True
        assert mgr.get_instance(instance_id)["name"] == "New Name"


def test_favorite():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = InstanceManager(base_dir=tmp)
        instance_id = mgr.create_instance("Fav Test", "1.20.1")
        assert mgr.get_instance(instance_id)["favorite"] is False
        mgr.set_favorite(instance_id, True)
        assert mgr.get_instance(instance_id)["favorite"] is True
        favs = mgr.get_favorites()
        assert instance_id in favs


def test_play_stats():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = InstanceManager(base_dir=tmp)
        instance_id = mgr.create_instance("Stats Test", "1.20.1")
        mgr.update_play_stats(instance_id, 3600)
        inst = mgr.get_instance(instance_id)
        assert inst["play_count"] == 1
        assert inst["total_playtime"] == 3600
        assert inst["last_played"] is not None


def test_recently_played():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = InstanceManager(base_dir=tmp)
        id1 = mgr.create_instance("First", "1.20.1")
        id2 = mgr.create_instance("Second", "1.20.1")
        mgr.update_play_stats(id2, 100)
        recent = mgr.get_recently_played(limit=5)
        assert len(recent) >= 1
        assert recent[0][0] == id2


def test_update_settings():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = InstanceManager(base_dir=tmp)
        instance_id = mgr.create_instance("Settings Test", "1.20.1")
        new_settings = {"ram_max": 8, "java_path": "C:\\java\\bin\\java.exe"}
        mgr.update_instance_settings(instance_id, new_settings)
        inst = mgr.get_instance(instance_id)
        assert inst["settings"]["ram_max"] == 8
        assert inst["settings"]["java_path"] == "C:\\java\\bin\\java.exe"


def test_get_instance_path():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = InstanceManager(base_dir=tmp)
        instance_id = mgr.create_instance("Path Test", "1.20.1")
        path = mgr.get_instance_path(instance_id)
        assert path is not None
        assert path.exists()
        assert (path / "mods").exists()
        assert (path / "saves").exists()
        assert (path / "config").exists()


def test_get_all_instances_empty():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = InstanceManager(base_dir=tmp)
        assert mgr.get_all_instances() == {}


def test_get_instance_size():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = InstanceManager(base_dir=tmp)
        instance_id = mgr.create_instance("Size Test", "1.20.1")
        size = mgr.get_instance_size(instance_id)
        assert size >= 0


def test_format_size():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = InstanceManager(base_dir=tmp)
        assert mgr.format_size(0) == "0.0 B"
        assert "KB" in mgr.format_size(1024)
        assert "MB" in mgr.format_size(1048576)
        assert "GB" in mgr.format_size(1073741824)


def test_import_export():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = InstanceManager(base_dir=tmp)
        orig_id = mgr.create_instance("Export Test", "1.20.1")
        export_path = os.path.join(tmp, "export.zip")
        assert mgr.export_instance(orig_id, export_path) is True
        assert os.path.exists(export_path)
        imported_id = mgr.import_instance(export_path, "Imported")
        assert imported_id is not None
        assert imported_id != orig_id
        assert mgr.get_instance(imported_id)["name"] == "Imported"


if __name__ == "__main__":
    test_create_instance()
    test_instance_persistence()
    test_delete_instance()
    test_duplicate_instance()
    test_rename_instance()
    test_favorite()
    test_play_stats()
    test_recently_played()
    test_update_settings()
    test_get_instance_path()
    test_get_all_instances_empty()
    test_get_instance_size()
    test_format_size()
    test_import_export()
    print("All instance_manager tests passed!")
