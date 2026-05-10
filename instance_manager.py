"""
Instance Manager for Drago Launcher
Handles creation, management, and isolation of Minecraft instances
"""
import os
import json
import shutil
import uuid
from pathlib import Path


class InstanceManager:
    def __init__(self, base_dir=None):
        """Initialize the instance manager"""
        if base_dir is None:
            base_dir = os.path.expandvars(r'%APPDATA%\.drago_launcher')
        
        self.base_dir = Path(base_dir)
        self.instances_dir = self.base_dir / "instances"
        self.instances_dir.mkdir(parents=True, exist_ok=True)
        
        # Config file for instance metadata
        self.config_file = self.base_dir / "instances.json"
        self.instances = self._load_instances()
    
    def _load_instances(self):
        """Load instance configurations from disk"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading instances: {e}")
                return {}
        return {}
    
    def _save_instances(self):
        """Save instance configurations to disk"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.instances, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving instances: {e}")
    
    def create_instance(self, name, version, loader="vanilla", loader_version=None):
        """
        Create a new instance
        
        Args:
            name: Display name for the instance
            version: Minecraft version (e.g., "1.20.1")
            loader: Mod loader type ("vanilla", "fabric", "forge", "quilt", "neoforge")
            loader_version: Version of the mod loader (optional)
        
        Returns:
            instance_id: Unique identifier for the instance
        """
        # Generate unique ID
        instance_id = str(uuid.uuid4())
        
        # Create instance directory structure
        instance_path = self.instances_dir / instance_id
        instance_path.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories for isolation
        subdirs = [
            "mods",
            "saves",
            "resourcepacks",
            "shaderpacks",
            "config",
            "logs",
            "screenshots",
            "crash-reports"
        ]
        
        for subdir in subdirs:
            (instance_path / subdir).mkdir(exist_ok=True)
        
        # Create instance metadata
        instance_data = {
            "id": instance_id,
            "name": name,
            "version": version,
            "loader": loader,
            "loader_version": loader_version,
            "created": self._get_timestamp(),
            "last_played": None,
            "play_count": 0,
            "total_playtime": 0,  # in seconds
            "favorite": False,
            "icon": None,  # path to custom icon
            "settings": {
                "java_path": None,  # Use default if None
                "ram_min": 2,
                "ram_max": 4,
                "resolution_width": 854,
                "resolution_height": 480,
                "fullscreen": False,
                "jvm_args": [],
                "game_args": []
            }
        }
        
        self.instances[instance_id] = instance_data
        self._save_instances()
        
        return instance_id
    
    def delete_instance(self, instance_id):
        """Delete an instance and all its data"""
        if instance_id not in self.instances:
            return False
        
        instance_path = self.instances_dir / instance_id
        
        try:
            if instance_path.exists():
                shutil.rmtree(instance_path)
            
            del self.instances[instance_id]
            self._save_instances()
            return True
        except Exception as e:
            print(f"Error deleting instance: {e}")
            return False
    
    def duplicate_instance(self, instance_id, new_name=None):
        """
        Duplicate an existing instance
        
        Args:
            instance_id: ID of instance to duplicate
            new_name: Name for the new instance (optional)
        
        Returns:
            new_instance_id: ID of the duplicated instance
        """
        if instance_id not in self.instances:
            return None
        
        original = self.instances[instance_id]
        
        # Create new instance with same settings
        new_id = str(uuid.uuid4())
        new_instance_path = self.instances_dir / new_id
        original_path = self.instances_dir / instance_id
        
        try:
            # Copy entire directory structure
            shutil.copytree(original_path, new_instance_path)
            
            # Create new metadata
            new_data = original.copy()
            new_data["id"] = new_id
            new_data["name"] = new_name or f"{original['name']} (Copy)"
            new_data["created"] = self._get_timestamp()
            new_data["last_played"] = None
            new_data["play_count"] = 0
            new_data["total_playtime"] = 0
            new_data["settings"] = original["settings"].copy()
            
            self.instances[new_id] = new_data
            self._save_instances()
            
            return new_id
        except Exception as e:
            print(f"Error duplicating instance: {e}")
            return None
    
    def rename_instance(self, instance_id, new_name):
        """Rename an instance"""
        if instance_id not in self.instances:
            return False
        
        self.instances[instance_id]["name"] = new_name
        self._save_instances()
        return True
    
    def get_instance(self, instance_id):
        """Get instance data"""
        return self.instances.get(instance_id)
    
    def get_all_instances(self):
        """Get all instances"""
        return self.instances
    
    def get_instance_path(self, instance_id):
        """Get the filesystem path for an instance"""
        if instance_id not in self.instances:
            return None
        return self.instances_dir / instance_id
    
    def update_instance_settings(self, instance_id, settings):
        """Update instance settings"""
        if instance_id not in self.instances:
            return False
        
        self.instances[instance_id]["settings"].update(settings)
        self._save_instances()
        return True
    
    def set_favorite(self, instance_id, favorite=True):
        """Mark instance as favorite"""
        if instance_id not in self.instances:
            return False
        
        self.instances[instance_id]["favorite"] = favorite
        self._save_instances()
        return True
    
    def update_play_stats(self, instance_id, playtime_seconds=0):
        """Update play statistics for an instance"""
        if instance_id not in self.instances:
            return False
        
        self.instances[instance_id]["last_played"] = self._get_timestamp()
        self.instances[instance_id]["play_count"] += 1
        self.instances[instance_id]["total_playtime"] += playtime_seconds
        self._save_instances()
        return True
    
    def set_custom_icon(self, instance_id, icon_path):
        """Set a custom icon for an instance"""
        if instance_id not in self.instances:
            return False
        
        instance_path = self.instances_dir / instance_id
        icon_dest = instance_path / "icon.png"
        
        try:
            shutil.copy(icon_path, icon_dest)
            self.instances[instance_id]["icon"] = str(icon_dest)
            self._save_instances()
            return True
        except Exception as e:
            print(f"Error setting icon: {e}")
            return False
    
    def export_instance(self, instance_id, export_path):
        """
        Export an instance as a shareable package
        
        Args:
            instance_id: ID of instance to export
            export_path: Path where to save the export (should end in .zip)
        
        Returns:
            bool: Success status
        """
        if instance_id not in self.instances:
            return False
        
        instance_path = self.instances_dir / instance_id
        
        try:
            # Create a zip archive
            shutil.make_archive(
                export_path.replace('.zip', ''),
                'zip',
                instance_path
            )
            return True
        except Exception as e:
            print(f"Error exporting instance: {e}")
            return False
    
    def import_instance(self, zip_path, name=None):
        """
        Import an instance from a zip file
        
        Args:
            zip_path: Path to the zip file
            name: Optional name for the imported instance
        
        Returns:
            instance_id: ID of the imported instance
        """
        new_id = str(uuid.uuid4())
        new_instance_path = self.instances_dir / new_id
        
        try:
            # Extract zip
            shutil.unpack_archive(zip_path, new_instance_path)
            
            # Try to read metadata if it exists
            metadata_file = new_instance_path / "instance.json"
            if metadata_file.exists():
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    imported_data = json.load(f)
            else:
                # Create basic metadata
                imported_data = {
                    "name": name or "Imported Instance",
                    "version": "1.20.1",
                    "loader": "vanilla",
                    "loader_version": None,
                    "settings": {
                        "java_path": None,
                        "ram_min": 2,
                        "ram_max": 4,
                        "resolution_width": 854,
                        "resolution_height": 480,
                        "fullscreen": False,
                        "jvm_args": [],
                        "game_args": []
                    }
                }
            
            # Update with new ID and timestamps
            imported_data["id"] = new_id
            imported_data["created"] = self._get_timestamp()
            imported_data["last_played"] = None
            imported_data["play_count"] = 0
            imported_data["total_playtime"] = 0
            imported_data["favorite"] = False
            
            if name:
                imported_data["name"] = name
            
            self.instances[new_id] = imported_data
            self._save_instances()
            
            return new_id
        except Exception as e:
            print(f"Error importing instance: {e}")
            # Clean up on failure
            if new_instance_path.exists():
                shutil.rmtree(new_instance_path)
            return None
    
    def get_recently_played(self, limit=5):
        """Get recently played instances"""
        instances_with_play = [
            (id, data) for id, data in self.instances.items()
            if data.get("last_played")
        ]
        
        # Sort by last_played timestamp
        instances_with_play.sort(
            key=lambda x: x[1]["last_played"],
            reverse=True
        )
        
        return instances_with_play[:limit]
    
    def get_favorites(self):
        """Get favorite instances"""
        return {
            id: data for id, data in self.instances.items()
            if data.get("favorite", False)
        }
    
    def _get_timestamp(self):
        """Get current timestamp as ISO string"""
        from datetime import datetime
        return datetime.now().isoformat()
    
    def get_instance_size(self, instance_id):
        """Calculate total size of an instance in bytes"""
        if instance_id not in self.instances:
            return 0
        
        instance_path = self.instances_dir / instance_id
        total_size = 0
        
        try:
            for dirpath, dirnames, filenames in os.walk(instance_path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    total_size += os.path.getsize(filepath)
        except Exception as e:
            print(f"Error calculating size: {e}")
        
        return total_size
    
    def format_size(self, bytes_size):
        """Format bytes to human-readable size"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} PB"
