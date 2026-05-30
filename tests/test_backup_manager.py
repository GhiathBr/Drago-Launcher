import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backup_manager import BackupManager


def test_create_and_restore_backup():
    with tempfile.TemporaryDirectory() as tmp:
        instances_dir = os.path.join(tmp, "instances")
        os.makedirs(instances_dir)
        mgr = BackupManager(instances_dir)

        instance_id = "test-instance-123"
        instance_path = os.path.join(instances_dir, instance_id)
        os.makedirs(os.path.join(instance_path, "mods"))
        os.makedirs(os.path.join(instance_path, "saves"))

        with open(os.path.join(instance_path, "mods", "test.jar"), "w") as f:
            f.write("test mod")
        with open(os.path.join(instance_path, "saves", "world"), "w") as f:
            f.write("test world")

        backup_id = mgr.create_backup(instance_id, "test backup")
        assert backup_id is not None

        os.remove(os.path.join(instance_path, "mods", "test.jar"))
        assert not os.path.exists(os.path.join(instance_path, "mods", "test.jar"))

        assert mgr.restore_backup(backup_id, instance_id) is True
        assert os.path.exists(os.path.join(instance_path, "mods", "test.jar"))


def test_get_backups_for_instance():
    with tempfile.TemporaryDirectory() as tmp:
        instances_dir = os.path.join(tmp, "instances")
        os.makedirs(instances_dir)
        mgr = BackupManager(instances_dir)

        instance_id = "test-instance"
        os.makedirs(os.path.join(instances_dir, instance_id))

        mgr.create_backup(instance_id, "backup 1")
        mgr.create_backup(instance_id, "backup 2")

        backups = mgr.get_backups_for_instance(instance_id)
        assert len(backups) == 2


def test_delete_backup():
    with tempfile.TemporaryDirectory() as tmp:
        instances_dir = os.path.join(tmp, "instances")
        os.makedirs(instances_dir)
        mgr = BackupManager(instances_dir)

        instance_id = "test-instance"
        os.makedirs(os.path.join(instances_dir, instance_id))

        backup_id = mgr.create_backup(instance_id, "to delete")
        assert mgr.delete_backup(backup_id) is True
        assert len(mgr.get_backups_for_instance(instance_id)) == 0


def test_format_size():
    assert BackupManager.format_size(0) == "0.0 B"
    assert BackupManager.format_size(1024) == "1.0 KB"
    assert BackupManager.format_size(1048576) == "1.0 MB"


if __name__ == "__main__":
    test_create_and_restore_backup()
    test_get_backups_for_instance()
    test_delete_backup()
    test_format_size()
    print("All backup_manager tests passed!")
