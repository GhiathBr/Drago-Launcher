import customtkinter as ctk
import minecraft_launcher_lib
import platform
import subprocess
import os
import sys
import threading
import queue
import asyncio
import json
from pathlib import Path
import requests
import warnings
from urllib3.exceptions import InsecureRequestWarning
from instance_manager import InstanceManager
from auth import XSTSIdentityManager, AuthError
from loader_installer import install_loader, get_loader_versions, AVAILABLE_LOADERS, get_loader_display_name
from java_manager import scan_java_installations, get_java_for_mc_version, suggest_java_for_instance
from backup_manager import BackupManager
from theme_manager import apply_theme, get_theme_names, THEMES, DEFAULT_THEME
from console_viewer import spawn_console
from modpack_manager import import_mrpack
from network_monitor import NetworkMonitor
from mineskin_browser import search_skins, get_trending_skins, apply_skin_from_mineskin, get_skin_render_url, get_skin_image_url
from shader_manager import KNOWN_SHADERS, get_shader_version_info, install_shader, list_installed_shaders
import portable as portable_mode
from conflict_scanner import scan_mods_directory, scan_resourcepacks_directory
from crash_analyzer import analyze_instance as analyze_crash_reports, find_crash_reports

# Try to load tkinterdnd2 for OS drag-and-drop support
try:
    from tkinterdnd2 import TkinterDnD
    _HAVE_DND = True
except ImportError:
    _HAVE_DND = False

# SSL verification: disabled by default for antivirus/firewall compatibility,
# but can be enabled in settings for security
SSL_VERIFY = os.environ.get("DRAGO_SSL_VERIFY", "0") == "1"
if not SSL_VERIFY:
    warnings.simplefilter('ignore', InsecureRequestWarning)
    original_request = requests.Session.request
    def patched_request(self, method, url, **kwargs):
        if "verify" not in kwargs:
            kwargs['verify'] = False
        return original_request(self, method, url, **kwargs)
    requests.Session.request = patched_request

# --- APP SETUP ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class DragoLauncher(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Drago Launcher - Safe & Clear")
        self.geometry("900x600")
        self.minsize(800, 500)
        
        self.CURRENT_VERSION = "v2.1.0"

        # --- Portable mode detection ---
        launcher_dir = os.path.dirname(os.path.abspath(sys.argv[0])) if getattr(sys, 'frozen', False) else os.getcwd()
        self.launcher_dir = launcher_dir
        self.using_portable = portable_mode.is_portable()

        # Determine minecraft directory and config location
        if self.using_portable:
            mine_dir = portable_mode.get_minecraft_dir(launcher_dir)
            self.config_file = os.path.join(launcher_dir, portable_mode.CONFIG_FILENAME)
        else:
            mine_dir = portable_mode.get_default_minecraft_dir()
            self.config_file = os.path.join(mine_dir, "drago_launcher_config.json")

        if not os.path.exists(mine_dir):
            os.makedirs(mine_dir, exist_ok=True)

        # Keep backward compatibility by moving an old config if it exists alongside the app
        old_config_file = os.path.join(launcher_dir, "drago_launcher_config.json")
        if os.path.exists(old_config_file) and not os.path.exists(self.config_file) and not self.using_portable:
            import shutil
            shutil.move(old_config_file, self.config_file)

        self.config = {
            "last_version": "", "memory": 6, "current_instance": None,
            "use_global_minecraft": True, "theme": DEFAULT_THEME,
            "safe_mode": False, "show_console": True, "ssl_verify": SSL_VERIFY,
            "portable_mode": self.using_portable, "auto_backup": True,
        }
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    self.config.update(json.load(f))
            except Exception:
                pass

        # Apply saved theme
        saved_theme = self.config.get("theme", DEFAULT_THEME)
        if saved_theme in THEMES:
            apply_theme(saved_theme)

        # Set default to global .minecraft if not explicitly configured
        if "use_global_minecraft" not in self.config:
            self.config["use_global_minecraft"] = True
            self._save_config()

        # Initialize Instance Manager (respect portable mode)
        if self.using_portable:
            data_dir = portable_mode.get_data_dir(launcher_dir)
            self.instance_manager = InstanceManager(base_dir=data_dir)
        else:
            self.instance_manager = InstanceManager()

        # Initialize Backup Manager
        instances_base = self.instance_manager.base_dir
        self.backup_manager = BackupManager(str(self.instance_manager.instances_dir))

        # Cache Java installations
        self.java_installations = scan_java_installations()
        self._java_scan_thread = None

        # Network monitor for silent refresh
        self.network_monitor = NetworkMonitor()
        self.network_monitor.add_listener(self._on_internet_restored)
        self.network_monitor.start()

        # Only create default instance if user explicitly chose instance mode
        if not self.config.get("use_global_minecraft"):
            if not self.instance_manager.get_all_instances():
                default_id = self.instance_manager.create_instance(
                    name="Default Instance",
                    version="1.20.1",
                    loader="vanilla"
                )
                self.config["current_instance"] = default_id
                self._save_config()

            # Set current instance
            if not self.config.get("current_instance"):
                instances = self.instance_manager.get_all_instances()
                if instances:
                    self.config["current_instance"] = list(instances.keys())[0]
                    self._save_config()

        # Main Grid Layout
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)

        self.setup_sidebar()
        self.setup_bottom_bar() # Need this loaded first for Username & Version variables
        
        # Create container for page swapping
        self.page_container = ctk.CTkFrame(self, fg_color="transparent")
        self.page_container.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.page_container.grid_columnconfigure(0, weight=1)
        self.page_container.grid_rowconfigure(0, weight=1)
        
        self.setup_main_feed()
        self.setup_content_browser()
        self.setup_instances_page()
        
        # Show News by default
        self.show_news_page()
        
        # Auto-check for updates silently on startup
        self.after(2000, lambda: self.check_for_updates(silent=True))

    def _get_global_minecraft_dir(self):
        return portable_mode.get_default_minecraft_dir()

    def show_news_page(self):
        self.content_browser_frame.grid_forget()
        self.instances_frame.grid_forget()
        self.main_frame.grid(row=0, column=0, sticky="nsew")
        
    def show_content_page(self):
        self.main_frame.grid_forget()
        self.instances_frame.grid_forget()
        self.content_browser_frame.grid(row=0, column=0, sticky="nsew")
    
    def show_instances_page(self):
        self.main_frame.grid_forget()
        self.content_browser_frame.grid_forget()
        self.instances_frame.grid(row=0, column=0, sticky="nsew")
        self.refresh_instances_list()

    def setup_sidebar(self):
        # Sidebar Frame
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1) # Push bottom buttons down

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="DRAGO", font=ctk.CTkFont(size=24, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))
        
        self.subtitle_label = ctk.CTkLabel(self.sidebar_frame, text="LAUNCHER", font=ctk.CTkFont(size=12))
        self.subtitle_label.grid(row=1, column=0, padx=20, pady=(0, 20))

        # Nav Buttons (Blue theme to match launcher aesthetic)
        self.btn_home = ctk.CTkButton(self.sidebar_frame, text="Home", fg_color="#1f538d", hover_color="#2980b9", anchor="w", command=self.show_news_page)
        self.btn_home.grid(row=2, column=0, padx=20, pady=10)
        
        self.btn_instances = ctk.CTkButton(self.sidebar_frame, text="Instances", fg_color="#1f538d", hover_color="#2980b9", anchor="w", command=self.show_instances_page)
        self.btn_instances.grid(row=3, column=0, padx=20, pady=10)

        self.btn_mods = ctk.CTkButton(self.sidebar_frame, text="Game Content Browser", fg_color="#1f538d", hover_color="#2980b9", anchor="w", command=self.show_content_page)
        self.btn_mods.grid(row=4, column=0, padx=20, pady=10)

        self.btn_update = ctk.CTkButton(self.sidebar_frame, text="Check for Updates", fg_color="#1f538d", hover_color="#2980b9", anchor="w", command=self.check_for_updates)
        self.btn_update.grid(row=5, column=0, padx=20, pady=10)

        self.btn_import_modpack = ctk.CTkButton(self.sidebar_frame, text="Import Modpack", fg_color="#1f538d", hover_color="#2980b9", anchor="w", command=self.import_modpack_dialog)
        self.btn_import_modpack.grid(row=6, column=0, padx=20, pady=10)

        self.btn_settings = ctk.CTkButton(self.sidebar_frame, text="Settings", fg_color="#1f538d", hover_color="#2980b9", anchor="w", command=self.open_settings)
        self.btn_settings.grid(row=7, column=0, padx=20, pady=20)

    def setup_instances_page(self):
        """Setup the instances management page"""
        self.instances_frame = ctk.CTkFrame(self.page_container, corner_radius=0, fg_color="transparent")
        self.instances_frame.grid_columnconfigure(0, weight=1)
        self.instances_frame.grid_rowconfigure(1, weight=1)
        
        # Header with actions
        header_frame = ctk.CTkFrame(self.instances_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header_frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(header_frame, text="Instances", font=ctk.CTkFont(size=20, weight="bold")).grid(row=0, column=0, sticky="w")
        
        # Action buttons
        btn_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        btn_frame.grid(row=0, column=1, sticky="e")
        
        ctk.CTkButton(btn_frame, text="+ New Instance", fg_color="#27ae60", hover_color="#2ecc71", 
                     command=self.create_new_instance_dialog, width=120).pack(side="left", padx=5)
        
        ctk.CTkButton(btn_frame, text="Import", fg_color="#3498db", hover_color="#2980b9",
                     command=self.import_instance_dialog, width=80).pack(side="left", padx=5)

        ctk.CTkButton(btn_frame, text="Export", fg_color="#e67e22", hover_color="#d35400",
                     command=self.export_instance_dialog, width=80).pack(side="left", padx=5)
        
        # Scrollable instances list
        self.instances_scroll = ctk.CTkScrollableFrame(self.instances_frame, fg_color="#1e1e1e")
        self.instances_scroll.grid(row=1, column=0, sticky="nsew")
        self.instances_scroll.grid_columnconfigure(0, weight=1)
    
    def refresh_instances_list(self):
        """Refresh the instances list display"""
        # Clear existing widgets
        for widget in self.instances_scroll.winfo_children():
            widget.destroy()
        
        instances = self.instance_manager.get_all_instances()
        current_id = self.config.get("current_instance")
        
        if not instances:
            ctk.CTkLabel(self.instances_scroll, text="No instances yet. Create one to get started!", 
                        text_color="#aaaaaa").grid(row=0, column=0, pady=50)
            return
        
        # Sort: favorites first, then by last played
        sorted_instances = sorted(
            instances.items(),
            key=lambda x: (
                not x[1].get("favorite", False),
                x[1].get("last_played") or ""
            ),
            reverse=True
        )
        
        for idx, (instance_id, data) in enumerate(sorted_instances):
            self._create_instance_card(instance_id, data, idx, current_id)
    
    def _create_instance_card(self, instance_id, data, row, current_id):
        """Create a card widget for an instance"""
        is_current = instance_id == current_id
        
        card = ctk.CTkFrame(self.instances_scroll, fg_color="#2b2b2b" if not is_current else "#1f538d", 
                           corner_radius=8, border_width=2, 
                           border_color="#27ae60" if is_current else "transparent")
        card.grid(row=row, column=0, sticky="ew", pady=5, padx=5)
        card.grid_columnconfigure(1, weight=1)
        
        # Icon placeholder (left side)
        icon_label = ctk.CTkLabel(card, text="🎮", font=ctk.CTkFont(size=32), width=60, height=60)
        icon_label.grid(row=0, column=0, rowspan=3, padx=10, pady=10)
        
        # Instance info (middle)
        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.grid(row=0, column=1, rowspan=3, sticky="nsew", padx=10, pady=10)
        info_frame.grid_columnconfigure(0, weight=1)
        
        # Name with favorite star
        name_text = f"⭐ {data['name']}" if data.get('favorite') else data['name']
        ctk.CTkLabel(info_frame, text=name_text, font=ctk.CTkFont(size=16, weight="bold"), 
                    anchor="w").grid(row=0, column=0, sticky="w")
        
        # Version and loader info
        loader_text = data['loader'].capitalize()
        if data.get('loader_version'):
            loader_text += f" {data['loader_version']}"
        
        version_info = f"Minecraft {data['version']} • {loader_text}"
        ctk.CTkLabel(info_frame, text=version_info, text_color="#aaaaaa", anchor="w").grid(row=1, column=0, sticky="w")
        
        # Stats
        play_count = data.get('play_count', 0)
        playtime = data.get('total_playtime', 0)
        hours = playtime // 3600
        minutes = (playtime % 3600) // 60
        
        stats_text = f"Played {play_count} times"
        if hours > 0:
            stats_text += f" • {hours}h {minutes}m"
        elif minutes > 0:
            stats_text += f" • {minutes}m"
        
        ctk.CTkLabel(info_frame, text=stats_text, text_color="#777777", anchor="w", 
                    font=ctk.CTkFont(size=11)).grid(row=2, column=0, sticky="w")
        
        # Action buttons (right side)
        actions_frame = ctk.CTkFrame(card, fg_color="transparent")
        actions_frame.grid(row=0, column=2, rowspan=3, padx=10, pady=10)
        
        if not is_current:
            ctk.CTkButton(actions_frame, text="Select", width=80, fg_color="#27ae60", hover_color="#2ecc71",
                         command=lambda: self.select_instance(instance_id)).pack(pady=2)
        else:
            ctk.CTkLabel(actions_frame, text="✓ Active", text_color="#27ae60", 
                        font=ctk.CTkFont(weight="bold")).pack(pady=2)
        
        ctk.CTkButton(actions_frame, text="Settings", width=80, fg_color="#3498db", hover_color="#2980b9",
                     command=lambda: self.open_instance_settings(instance_id)).pack(pady=2)
        
        ctk.CTkButton(actions_frame, text="Duplicate", width=80, fg_color="#9b59b6", hover_color="#8e44ad",
                     command=lambda: self.duplicate_instance(instance_id)).pack(pady=2)
        
        ctk.CTkButton(actions_frame, text="Delete", width=80, fg_color="#c0392b", hover_color="#e74c3c",
                     command=lambda: self.delete_instance_confirm(instance_id)).pack(pady=2)
    
    def select_instance(self, instance_id):
        """Select an instance as the current one"""
        self.config["current_instance"] = instance_id
        self._save_config()
        self.refresh_instances_list()
        self.update_play_button_text()
        self._update_ui_status(f"Switched to {self.instance_manager.get_instance(instance_id)['name']}", "#27ae60")
    
    def create_new_instance_dialog(self):
        """Open dialog to create a new instance"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Create New Instance")
        dialog.geometry("500x550")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        ctk.CTkLabel(dialog, text="Create New Instance", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=20)

        # Name
        ctk.CTkLabel(dialog, text="Instance Name:").pack(pady=(10, 0))
        name_entry = ctk.CTkEntry(dialog, width=350, placeholder_text="My Awesome Instance")
        name_entry.pack(pady=5)

        # Version
        ctk.CTkLabel(dialog, text="Minecraft Version:").pack(pady=(10, 0))
        version_var = ctk.StringVar(value="1.20.1")
        available_versions = ["1.20.1", "1.19.4", "1.18.2", "1.16.5", "1.12.2"]
        try:
            online_versions = [v['id'] for v in minecraft_launcher_lib.utils.get_version_list()
                             if v['type'] == 'release'][:30]
            available_versions = online_versions
        except:
            pass
        version_menu = ctk.CTkOptionMenu(dialog, variable=version_var, values=available_versions, width=350)
        version_menu.pack(pady=5)

        # Loader
        ctk.CTkLabel(dialog, text="Mod Loader:").pack(pady=(10, 0))
        loader_var = ctk.StringVar(value="vanilla")
        loader_menu = ctk.CTkOptionMenu(dialog, variable=loader_var,
                                       values=AVAILABLE_LOADERS, width=350)
        loader_menu.pack(pady=5)

        # Loader version (shown when non-vanilla selected)
        loader_version_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        loader_version_frame.pack(pady=5, fill="x", padx=20)
        loader_version_label = ctk.CTkLabel(loader_version_frame, text="Loader Version:", text_color="#aaaaaa")
        loader_version_var = ctk.StringVar(value="latest")
        loader_version_menu = ctk.CTkOptionMenu(loader_version_frame, variable=loader_version_var,
                                               values=["latest"], width=350)
        
        def on_loader_change(choice):
            if choice == "vanilla":
                loader_version_label.pack_forget()
                loader_version_menu.pack_forget()
            else:
                loader_version_label.pack(pady=(5, 0))
                loader_version_menu.pack(pady=5)
                loader_version_menu.configure(values=["Fetching..."])
                loader_version_var.set("Fetching...")
                threading.Thread(target=lambda: _fetch_loader_versions(choice), daemon=True).start()

        def _fetch_loader_versions(loader):
            try:
                mc_ver = version_var.get()
                versions = get_loader_versions(loader, mc_ver)
                def update():
                    if versions:
                        items = [v["display"] for v in versions[:20]]
                        loader_version_menu.configure(values=items)
                        loader_version_var.set(items[0] if items else "latest")
                    else:
                        loader_version_menu.configure(values=["latest"])
                        loader_version_var.set("latest")
                self.after(0, update)
            except Exception as e:
                self.after(0, lambda: loader_version_menu.configure(values=["latest"]) or loader_version_var.set("latest"))

        loader_menu.configure(command=on_loader_change)

        def on_version_change(choice):
            if loader_var.get() != "vanilla":
                threading.Thread(target=lambda: _fetch_loader_versions(loader_var.get()), daemon=True).start()

        version_menu.configure(command=on_version_change)

        # Java info (auto-detected)
        java_info_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        java_info_frame.pack(pady=5, fill="x", padx=20)
        java_info_label = ctk.CTkLabel(java_info_frame, text="", text_color="#aaaaaa", font=ctk.CTkFont(size=11))

        def _update_java_info(*args):
            mc_ver = version_var.get()
            needed = get_java_for_mc_version(mc_ver)
            java_info_label.configure(text=f"Requires Java {needed}+  |  {len(self.java_installations)} Java(s) detected")
            java_info_label.pack()

        version_var.trace_add("write", _update_java_info)
        self.after(100, _update_java_info)

        # Buttons
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=20)

        def create():
            name = name_entry.get().strip()
            if not name:
                name = f"Instance {len(self.instance_manager.get_all_instances()) + 1}"

            loader = loader_var.get()
            loader_ver = None
            if loader != "vanilla" and loader_version_var.get() != "latest":
                loader_ver = loader_version_var.get()

            instance_id = self.instance_manager.create_instance(
                name=name,
                version=version_var.get(),
                loader=loader,
                loader_version=loader_ver,
            )

            self.config["current_instance"] = instance_id
            self._save_config()
            self.refresh_instances_list()
            dialog.destroy()
            self._update_ui_status(f"Created instance: {name}", "#27ae60")

        ctk.CTkButton(btn_frame, text="Create", fg_color="#27ae60", hover_color="#2ecc71",
                     command=create, width=120).pack(side="left", padx=10)

        ctk.CTkButton(btn_frame, text="Cancel", fg_color="#555555", hover_color="#444444",
                     command=dialog.destroy, width=120).pack(side="left", padx=10)
    
    def duplicate_instance(self, instance_id):
        """Duplicate an instance"""
        original = self.instance_manager.get_instance(instance_id)
        new_id = self.instance_manager.duplicate_instance(instance_id)
        
        if new_id:
            self.refresh_instances_list()
            self._update_ui_status(f"Duplicated {original['name']}", "#27ae60")
        else:
            self._update_ui_status("Failed to duplicate instance", "#e74c3c")
    
    def delete_instance_confirm(self, instance_id):
        """Confirm and delete an instance"""
        instance = self.instance_manager.get_instance(instance_id)
        
        dialog = ctk.CTkToplevel(self)
        dialog.title("Confirm Delete")
        dialog.geometry("420x220")  # Increased slightly
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        
        ctk.CTkLabel(dialog, text="⚠️ Delete Instance?", font=ctk.CTkFont(size=18, weight="bold"),
                    text_color="#e74c3c").pack(pady=20)
        
        ctk.CTkLabel(dialog, text=f"Are you sure you want to delete\n'{instance['name']}'?\n\nThis will delete all mods, saves, and configs.",
                    wraplength=350).pack(pady=10)
        
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=20)
        
        def confirm_delete():
            # If deleting current instance, switch to another
            if instance_id == self.config.get("current_instance"):
                remaining = [id for id in self.instance_manager.get_all_instances().keys() if id != instance_id]
                if remaining:
                    self.config["current_instance"] = remaining[0]
                else:
                    self.config["current_instance"] = None
                self._save_config()
            
            if self.instance_manager.delete_instance(instance_id):
                self.refresh_instances_list()
                self._update_ui_status(f"Deleted {instance['name']}", "#27ae60")
            else:
                self._update_ui_status("Failed to delete instance", "#e74c3c")
            
            dialog.destroy()
        
        ctk.CTkButton(btn_frame, text="Delete", fg_color="#c0392b", hover_color="#e74c3c",
                     command=confirm_delete, width=120).pack(side="left", padx=10)
        
        ctk.CTkButton(btn_frame, text="Cancel", fg_color="#555555", hover_color="#444444",
                     command=dialog.destroy, width=120).pack(side="left", padx=10)
    
    def open_instance_settings(self, instance_id):
        """Open settings dialog for an instance"""
        instance = self.instance_manager.get_instance(instance_id)
        settings = instance['settings']

        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Settings - {instance['name']}")
        dialog.geometry("560x900")
        dialog.transient(self)
        dialog.resizable(False, False)

        main_container = ctk.CTkFrame(dialog, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=20, pady=20)
        main_container.grid_rowconfigure(0, weight=1)
        main_container.grid_columnconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(main_container, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")

        ctk.CTkLabel(scroll, text=f"Instance Settings", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(0, 20))

        # Name
        ctk.CTkLabel(scroll, text="Instance Name:", anchor="w").pack(fill="x", pady=(10, 0))
        name_entry = ctk.CTkEntry(scroll, width=400)
        name_entry.insert(0, instance['name'])
        name_entry.pack(pady=5)

        # Favorite toggle
        favorite_var = ctk.BooleanVar(value=instance.get('favorite', False))
        ctk.CTkCheckBox(scroll, text="⭐ Mark as Favorite", variable=favorite_var).pack(pady=5)

        # RAM Settings
        ctk.CTkLabel(scroll, text="RAM Allocation:", anchor="w", font=ctk.CTkFont(weight="bold")).pack(fill="x", pady=(15, 5))

        ram_min_var = ctk.IntVar(value=settings.get('ram_min', 2))
        ram_max_var = ctk.IntVar(value=settings.get('ram_max', 4))

        ctk.CTkLabel(scroll, text="Minimum RAM (GB):").pack(pady=(5, 0))
        ram_min_slider = ctk.CTkSlider(scroll, from_=1, to=16, number_of_steps=15, variable=ram_min_var)
        ram_min_slider.pack(pady=5)
        ram_min_label = ctk.CTkLabel(scroll, text=f"{ram_min_var.get()} GB")
        ram_min_label.pack()

        ctk.CTkLabel(scroll, text="Maximum RAM (GB):").pack(pady=(10, 0))
        ram_max_slider = ctk.CTkSlider(scroll, from_=2, to=32, number_of_steps=30, variable=ram_max_var)
        ram_max_slider.pack(pady=5)
        ram_max_label = ctk.CTkLabel(scroll, text=f"{ram_max_var.get()} GB")
        ram_max_label.pack()

        def update_ram_labels(val):
            ram_min_label.configure(text=f"{int(ram_min_var.get())} GB")
            ram_max_label.configure(text=f"{int(ram_max_var.get())} GB")

        ram_min_slider.configure(command=update_ram_labels)
        ram_max_slider.configure(command=update_ram_labels)

        # Resolution
        ctk.CTkLabel(scroll, text="Window Resolution:", anchor="w", font=ctk.CTkFont(weight="bold")).pack(fill="x", pady=(15, 5))

        res_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        res_frame.pack(fill="x", pady=5)

        width_var = ctk.StringVar(value=str(settings.get('resolution_width', 854)))
        height_var = ctk.StringVar(value=str(settings.get('resolution_height', 480)))

        ctk.CTkEntry(res_frame, textvariable=width_var, width=100, placeholder_text="Width").pack(side="left", padx=5)
        ctk.CTkLabel(res_frame, text="×").pack(side="left")
        ctk.CTkEntry(res_frame, textvariable=height_var, width=100, placeholder_text="Height").pack(side="left", padx=5)

        fullscreen_var = ctk.BooleanVar(value=settings.get('fullscreen', False))
        ctk.CTkCheckBox(scroll, text="Start in Fullscreen", variable=fullscreen_var).pack(pady=5)

        # --- Java Section ---
        ctk.CTkLabel(scroll, text="Java Settings:", anchor="w", font=ctk.CTkFont(weight="bold")).pack(fill="x", pady=(15, 5))

        mc_version = instance.get("version", "1.20.1")
        required_java = get_java_for_mc_version(mc_version)

        java_info_text = f"MC {mc_version} requires Java {required_java}+"
        if self.java_installations:
            detected = [j for j in self.java_installations if j["version"] == required_java]
            if detected:
                java_info_text += f"  ✓ Java {required_java} found: {detected[0]['vendor']}"
            else:
                versions = {j["version"] for j in self.java_installations}
                java_info_text += f"  ⚠ Found: Java {', '.join(str(v) for v in sorted(versions))}"
        else:
            java_info_text += "  ⚠ No Java detected on system"

        ctk.CTkLabel(scroll, text=java_info_text, text_color="#aaaaaa", font=ctk.CTkFont(size=11)).pack(pady=5)

        # Java Path
        ctk.CTkLabel(scroll, text="Java Path (leave empty for auto-detect):", anchor="w").pack(fill="x", pady=(5, 0))
        java_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        java_frame.pack(fill="x", pady=5)
        java_entry = ctk.CTkEntry(java_frame, width=320, placeholder_text="Auto-detect")
        if settings.get('java_path'):
            java_entry.insert(0, settings['java_path'])
        java_entry.pack(side="left", padx=(0, 5))

        def browse_java():
            from tkinter import filedialog
            path = filedialog.askopenfilename(title="Select Java Executable",
                                              filetypes=[("Java", "java.exe"), ("All Files", "*.*")])
            if path:
                java_entry.delete(0, "end")
                java_entry.insert(0, path)
        ctk.CTkButton(java_frame, text="Browse", width=70, fg_color="#3498db",
                      command=browse_java).pack(side="left")

        # Safe Mode toggle
        ctk.CTkLabel(scroll, text="Launch Options:", anchor="w", font=ctk.CTkFont(weight="bold")).pack(fill="x", pady=(15, 5))
        safe_mode_var = ctk.BooleanVar(value=instance.get('settings', {}).get('safe_mode', False))
        ctk.CTkCheckBox(scroll, text="🔒 Safe Mode (launch without mods/shaders/resourcepacks)",
                        variable=safe_mode_var).pack(pady=5)

        # --- Backup Section ---
        ctk.CTkLabel(scroll, text="Backups:", anchor="w", font=ctk.CTkFont(weight="bold")).pack(fill="x", pady=(15, 5))

        backup_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        backup_frame.pack(fill="x", pady=5)

        backup_count = len(self.backup_manager.get_backups_for_instance(instance_id))
        ctk.CTkLabel(backup_frame, text=f"{backup_count} backup(s) for this instance",
                     text_color="#aaaaaa").pack(side="left", padx=(0, 10))

        def do_backup():
            def _backup():
                bid = self.backup_manager.create_backup(instance_id, name=f"Manual {instance['name']}")
                if bid:
                    self.after(0, lambda: self._update_ui_status(f"Backup created!", "#27ae60"))
                else:
                    self.after(0, lambda: self._update_ui_status("Backup failed", "#e74c3c"))
            threading.Thread(target=_backup, daemon=True).start()

        ctk.CTkButton(backup_frame, text="Backup Now", width=100, fg_color="#e67e22",
                     command=do_backup).pack(side="left", padx=5)

        def restore_backup():
            backups = self.backup_manager.get_backups_for_instance(instance_id)
            if not backups:
                self._update_ui_status("No backups to restore", "#e74c3c")
                return
            latest = backups[0]
            if self.backup_manager.restore_backup(latest["id"], instance_id):
                self._update_ui_status(f"Restored from {latest['name']}", "#27ae60")
            else:
                self._update_ui_status("Restore failed", "#e74c3c")

        ctk.CTkButton(backup_frame, text="Restore Latest", width=100, fg_color="#9b59b6",
                     command=restore_backup).pack(side="left", padx=5)

        # Save button - OUTSIDE scroll frame, fixed at bottom
        def save_settings():
            new_settings = {
                'ram_min': int(ram_min_var.get()),
                'ram_max': int(ram_max_var.get()),
                'resolution_width': int(width_var.get()) if width_var.get().isdigit() else 854,
                'resolution_height': int(height_var.get()) if height_var.get().isdigit() else 480,
                'fullscreen': fullscreen_var.get(),
                'java_path': java_entry.get().strip() or None,
                'jvm_args': settings.get('jvm_args', []),
                'game_args': settings.get('game_args', []),
                'safe_mode': safe_mode_var.get(),
            }

            self.instance_manager.update_instance_settings(instance_id, new_settings)
            self.instance_manager.rename_instance(instance_id, name_entry.get().strip())
            self.instance_manager.set_favorite(instance_id, favorite_var.get())

            self.refresh_instances_list()
            dialog.destroy()
            self._update_ui_status("Settings saved", "#27ae60")

        button_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        button_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))

        ctk.CTkButton(button_frame, text="Save Settings", fg_color="#27ae60", hover_color="#2ecc71",
                     command=save_settings, width=200, height=40).pack(pady=10)
    
    def import_instance_dialog(self):
        """Import an instance from a zip file"""
        from tkinter import filedialog
        
        filepath = filedialog.askopenfilename(
            title="Select Instance Package",
            filetypes=[("ZIP Files", "*.zip"), ("All Files", "*.*")]
        )
        
        if filepath:
            instance_id = self.instance_manager.import_instance(filepath)
            if instance_id:
                self.refresh_instances_list()
                self._update_ui_status("Instance imported successfully", "#27ae60")
            else:
                self._update_ui_status("Failed to import instance", "#e74c3c")

    def export_instance_dialog(self):
        """Export an instance as a zip file"""
        from tkinter import filedialog
        
        current_id = self.config.get("current_instance")
        if not current_id:
            self._update_ui_status("No instance selected to export", "#e74c3c")
            return
        
        instance = self.instance_manager.get_instance(current_id)
        if not instance:
            self._update_ui_status("Instance not found", "#e74c3c")
            return
        
        filepath = filedialog.asksaveasfilename(
            title="Export Instance",
            defaultextension=".zip",
            filetypes=[("ZIP Files", "*.zip")],
            initialfile=f"{instance['name']}.zip"
        )
        
        if filepath:
            success = self.instance_manager.export_instance(current_id, filepath)
            if success:
                self._update_ui_status(f"Exported {instance['name']}", "#27ae60")
            else:
                self._update_ui_status("Failed to export instance", "#e74c3c")

    def import_modpack_dialog(self):
        """Import a Modrinth modpack (.mrpack)"""
        from tkinter import filedialog, simpledialog
        
        filepath = filedialog.askopenfilename(
            title="Select Modrinth Modpack",
            filetypes=[("Modrinth Modpack", "*.mrpack"), ("ZIP Files", "*.zip"), ("All Files", "*.*")]
        )
        
        if not filepath:
            return
        
        self._update_ui_status("Importing modpack...", "#f39c12")
        
        def do_import():
            current_id = self.config.get("current_instance")
            if not current_id:
                self._update_ui_status("Select an instance first!", "#e74c3c")
                return
            
            instance_path = self.instance_manager.get_instance_path(current_id)
            if not instance_path:
                self._update_ui_status("Instance not found!", "#e74c3c")
                return
            
            success, result = import_mrpack(filepath, str(instance_path))
            
            if success:
                self._update_ui_status(f"Modpack '{result}' imported!", "#27ae60")
                self.after(0, self.load_installed_content)
            else:
                self._update_ui_status(f"Import failed: {result}", "#e74c3c")
        
        threading.Thread(target=do_import, daemon=True).start()
    
    def _save_config(self):
        """Save launcher config to disk"""
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")

    def setup_content_browser(self):
        self.content_browser_frame = ctk.CTkFrame(self.page_container, corner_radius=0, fg_color="transparent")
        self.content_browser_frame.grid_columnconfigure(0, weight=1)
        self.content_browser_frame.grid_rowconfigure(1, weight=1)

        header_label = ctk.CTkLabel(self.content_browser_frame, text="Game Content Browser", font=ctk.CTkFont(size=20, weight="bold"))
        header_label.grid(row=0, column=0, sticky="w", pady=(0, 10))

        tabview = ctk.CTkTabview(self.content_browser_frame)
        tabview.grid(row=1, column=0, sticky="nsew")

        tabview.add("Skins")
        tabview.add("Modrinth Mods")
        tabview.add("Modrinth Worlds")
        tabview.add("Shaders")
        tabview.add("Installed Content")

        # ========================================
                # ========================================
        # === SKINS TAB (Vertical Layout) ===
        # ========================================
        skin_tab = tabview.tab("Skins")
        skin_tab.grid_columnconfigure(0, weight=0)  # Left panel (fixed)
        skin_tab.grid_columnconfigure(1, weight=1)  # Right panel (expandable)
        skin_tab.grid_rowconfigure(0, weight=1)

        # LEFT PANEL - Skin Preview (220px wide)
        left_panel = ctk.CTkFrame(skin_tab, fg_color="#1e1e1e", width=220)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        left_panel.grid_propagate(False)
        
        ctk.CTkLabel(left_panel, text="Current Skin", font=ctk.CTkFont(size=13, weight="bold"), 
                    text_color="#3498db").pack(pady=(10, 5))

        self.skin_preview_label = ctk.CTkLabel(left_panel, text="Loading...")
        self.skin_preview_label.pack(pady=10)

        def browse_skin():
            from tkinter import filedialog
            import shutil
            filepath = filedialog.askopenfilename(title="Select Skin", filetypes=[("PNG Files", "*.png")])
            if filepath:
                username = self.username_entry.get().strip() or "DRAGO"
                mine_dir = self._get_global_minecraft_dir()
                skin_dir = os.path.join(mine_dir, "CustomSkinLoader", "LocalSkin", "skins")
                os.makedirs(skin_dir, exist_ok=True)
                target_path = os.path.join(skin_dir, f"{username}.png")
                try:
                    shutil.copy(filepath, target_path)
                    csl_config_dir = os.path.join(mine_dir, "CustomSkinLoader")
                    os.makedirs(csl_config_dir, exist_ok=True)
                    csl_config_path = os.path.join(csl_config_dir, "CustomSkinLoader.json")
                    config_data = {"version": "14.0", "enable": True, "loadlist": [{"name": "LocalSkin", "type": "LocalSkin"}, {"name": "Mojang", "type": "MojangAPI"}]}
                    with open(csl_config_path, "w") as f:
                        json.dump(config_data, f, indent=4)
                    skin_status.configure(text="✓ Applied!", text_color="#27ae60")
                    self.load_visual_skin()
                except Exception as e:
                    skin_status.configure(text=f"Error: {e}", text_color="#e74c3c")

        ctk.CTkButton(left_panel, text="📁 Upload Skin", fg_color="#8e44ad", hover_color="#9b59b6", command=browse_skin).pack(pady=5, padx=10, fill="x")
        ctk.CTkButton(left_panel, text="🔄 Reload", fg_color="#3498db", hover_color="#2980b9", command=self.load_visual_skin).pack(pady=5, padx=10, fill="x")

        skin_status = ctk.CTkLabel(left_panel, text="", wraplength=180)
        skin_status.pack(pady=10)

        # RIGHT PANEL - Browser
        right_panel = ctk.CTkFrame(skin_tab, fg_color="transparent")
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        right_panel.grid_columnconfigure(0, weight=1)
        right_panel.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(right_panel, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(header, text="🎨 Browse Skins", font=ctk.CTkFont(size=14, weight="bold"), text_color="#3498db").grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(header, text="Community skins or upload custom", text_color="#aaaaaa", font=ctk.CTkFont(size=11)).grid(row=1, column=0, sticky="w", pady=(2,10))

        search_row = ctk.CTkFrame(header, fg_color="transparent")
        search_row.grid(row=2, column=0, sticky="ew")
        search_row.grid_columnconfigure(0, weight=1)

        search_entry = ctk.CTkEntry(search_row, placeholder_text="Search...")
        search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        results_scroll = ctk.CTkScrollableFrame(right_panel, fg_color="#1e1e1e")
        results_scroll.grid(row=1, column=0, sticky="nsew")
        results_scroll.grid_columnconfigure(0, weight=1)

        self.mineskin_results_container = ctk.CTkFrame(results_scroll, fg_color="transparent")
        self.mineskin_results_container.pack(fill="both", expand=True, padx=10, pady=10)
        self.mineskin_results_container.grid_columnconfigure(0, weight=1)

        def do_search(query=None):
            q = search_entry.get().strip() if query is None else query
            for w in self.mineskin_results_container.winfo_children():
                w.destroy()
            ctk.CTkLabel(self.mineskin_results_container, text="🔍 Searching...", text_color="#3498db").grid(row=0, column=0, pady=20)
            def _search():
                try:
                    skins = search_skins(q) if q else get_trending_skins()
                    def render():
                        for w in self.mineskin_results_container.winfo_children():
                            w.destroy()
                        if not skins:
                            ctk.CTkLabel(self.mineskin_results_container, text="⚠️ No skins available\n\nUse upload button instead", text_color="#e74c3c").grid(row=0, column=0, pady=20)
                            return
                        for i, s in enumerate(skins[:20]):
                            sid = s.get("id", 0)
                            name = s.get("name", f"Skin #{sid}")
                            card = ctk.CTkFrame(self.mineskin_results_container, fg_color="#2b2b2b", corner_radius=5)
                            card.grid(row=i, column=0, sticky="ew", pady=3)
                            card.grid_columnconfigure(0, weight=1)
                            ctk.CTkLabel(card, text=name, font=ctk.CTkFont(weight="bold"), anchor="w").grid(row=0, column=0, sticky="w", padx=10, pady=5)
                            def apply(sid=sid, sname=name):
                                username = self.username_entry.get().strip() or "DRAGO"
                                ok, msg = apply_skin_from_mineskin(sid, username, self._get_global_minecraft_dir())
                                self._update_ui_status(msg, "#27ae60" if ok else "#e74c3c")
                                if ok:
                                    skin_status.configure(text=f"✓ {sname}", text_color="#27ae60")
                                    self.load_visual_skin()
                            ctk.CTkButton(card, text="Apply", width=90, fg_color="#27ae60", hover_color="#2ecc71", command=apply).grid(row=0, column=1, padx=10, pady=5)
                    self.after(0, render)
                except Exception as e:
                    self.after(0, lambda: ctk.CTkLabel(self.mineskin_results_container, text=f"Error: {e}", text_color="#e74c3c").grid(row=0, column=0, pady=20))
            threading.Thread(target=_search, daemon=True).start()

        ctk.CTkButton(search_row, text="🔍 Search", width=80, fg_color="#3498db", hover_color="#2980b9", command=do_search).grid(row=0, column=1, padx=(0, 2))
        ctk.CTkButton(search_row, text="🔥 Trending", width=90, fg_color="#e67e22", hover_color="#d35400", command=lambda: do_search("")).grid(row=0, column=2)

        self.after(500, self.load_visual_skin)
        self.after(1000, lambda: do_search(""))

        # === MODRINTH MODS TAB ===
        # ========================================
        self._setup_modrinth_tab(tabview.tab("Modrinth Mods"), "mod")
        # ========================================
        # === MODRINTH WORLDS TAB ===
        # ========================================
        self._setup_modrinth_tab(tabview.tab("Modrinth Worlds"), "modpack")

        # ========================================
        # === SHADER BROWSER TAB ===
        # ========================================
        self._setup_modrinth_tab(tabview.tab("Shaders"), "shader")

        # ========================================
        # === INSTALLED CONTENT TAB ===
        # ========================================
        installed_tab = tabview.tab("Installed Content")
        installed_tab.grid_columnconfigure(0, weight=1)
        installed_tab.grid_rowconfigure(1, weight=1)

        self.installed_top_frame = ctk.CTkFrame(installed_tab, fg_color="transparent")
        self.installed_top_frame.grid(row=0, column=0, sticky="ew", pady=5)
        self.installed_top_frame.grid_columnconfigure(0, weight=1)

        refresh_btn = ctk.CTkButton(self.installed_top_frame, text="Refresh Installed List", fg_color="#e67e22", hover_color="#d35400", command=self.load_installed_content)
        refresh_btn.grid(row=0, column=1, padx=5)

        scan_btn = ctk.CTkButton(self.installed_top_frame, text="Scan Conflicts", fg_color="#e74c3c", hover_color="#c0392b",
                                command=lambda: threading.Thread(target=self._scan_mod_conflicts, daemon=True).start())
        scan_btn.grid(row=0, column=2, padx=5)

        crash_btn = ctk.CTkButton(self.installed_top_frame, text="Crash Reports", fg_color="#9b59b6", hover_color="#8e44ad",
                                 command=lambda: threading.Thread(target=self._show_crash_reports, daemon=True).start())
        crash_btn.grid(row=0, column=3, padx=5)

        self.installed_scroll = ctk.CTkScrollableFrame(installed_tab, fg_color="#1e1e1e")
        self.installed_scroll.grid(row=1, column=0, sticky="nsew", pady=5)
        self.installed_scroll.grid_columnconfigure(0, weight=1)

        self.load_installed_content()

    def _setup_modrinth_tab(self, parent_tab, search_type):
        parent_tab.grid_columnconfigure(0, weight=1)
        parent_tab.grid_rowconfigure(2, weight=1)

        prefix = "mods_" if search_type == "mod" else "worlds_" if search_type == "modpack" else "shaders_"
        label_prefix = "Mods" if search_type == "mod" else "Worlds/Modpacks" if search_type == "modpack" else "Shaders"
        no_found_msg = f"No {label_prefix} found"

        setattr(self, f"{prefix}version_label",
                ctk.CTkLabel(parent_tab, text=f"Browsing {label_prefix} for: Minecraft 1.21.1",
                            font=ctk.CTkFont(size=12, weight="bold"), text_color="#3498db"))
        getattr(self, f"{prefix}version_label").grid(row=0, column=0, sticky="w", padx=5, pady=(5, 0))

        setattr(self, f"{prefix}loader_warning",
                ctk.CTkLabel(parent_tab, text="", font=ctk.CTkFont(size=11), text_color="#e74c3c"))
        getattr(self, f"{prefix}loader_warning").grid(row=0, column=0, sticky="e", padx=5, pady=(5, 0))

        search_frame = ctk.CTkFrame(parent_tab, fg_color="transparent")
        search_frame.grid(row=1, column=0, sticky="ew", pady=5)
        search_frame.grid_columnconfigure(0, weight=1)

        search_entry = ctk.CTkEntry(search_frame, placeholder_text=f"Search {label_prefix}...")
        search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        search_btn = ctk.CTkButton(search_frame, text="Search", width=80)
        search_btn.grid(row=0, column=1)

        # FIX: Changed from scroll to auto - only show scrollbar when content overflows
        results_frame = ctk.CTkScrollableFrame(parent_tab, fg_color="#1e1e1e")
        results_frame.grid(row=2, column=0, sticky="nsew", pady=5)
        results_frame.grid_columnconfigure(0, weight=1)

        detail_frame = ctk.CTkScrollableFrame(parent_tab, fg_color="#1e1e1e")
        detail_frame.grid_columnconfigure(0, weight=1)

        def do_search(init_query=None, offset=0):
            def clear_widgets():
                for w in results_frame.winfo_children():
                    w.destroy()
            self.after(0, clear_widgets)

            import urllib.parse, re
            query = search_entry.get().strip() if init_query is None else init_query
            display_version = self.version_var.get()
            raw_version = self.version_id_to_display.get(display_version, display_version)
            target_version = "1.20.1"
            mine_dir = self._get_global_minecraft_dir()
            vjp = os.path.join(mine_dir, "versions", raw_version, f"{raw_version}.json")
            if os.path.exists(vjp):
                try:
                    vd = json.load(open(vjp))
                    if 'inheritsFrom' in vd:
                        target_version = vd['inheritsFrom']
                    elif 'id' in vd and re.match(r'^\d+\.\d+(?:\.\d+)?$', vd['id']):
                        target_version = vd['id']
                except: pass
            if target_version == "1.20.1":
                if "-" in raw_version:
                    for p in reversed(raw_version.split("-")):
                        if re.match(r'^\d+\.\d+(?:\.\d+)?$', p):
                            target_version = p; break
                elif re.match(r'^\d+\.\d+(?:\.\d+)?$', raw_version):
                    target_version = raw_version

            is_vanilla = search_type == "mod" and not any(l in raw_version.lower() for l in ['fabric','forge','quilt','neoforge'])
            self.after(0, lambda: getattr(self, f"{prefix}version_label").configure(
                text=f"Browsing {label_prefix} for: Minecraft {target_version} (Page {offset//15+1})"))
            if search_type == "mod":
                if is_vanilla:
                    self.after(0, lambda: getattr(self, f"{prefix}loader_warning").configure(
                        text="⚠️ Vanilla - Install Fabric/Forge!", text_color="#e74c3c"))
                else:
                    self.after(0, lambda: getattr(self, f"{prefix}loader_warning").configure(text="✓ Mod loader OK", text_color="#27ae60"))

            def show_status(txt):
                self.after(0, lambda: ctk.CTkLabel(results_frame, text=txt).grid(row=0, column=0, pady=20))
            show_status(f"Searching...")

            try:
                if search_type == "mod":
                    is_vanilla = not any(l in raw_version.lower() for l in ['fabric','forge','quilt','neoforge'])
                    lower_raw = raw_version.lower()
                    if "forge" in lower_raw and "neoforge" not in lower_raw:
                        active_loader = "forge"
                    elif "neoforge" in lower_raw:
                        active_loader = "neoforge"
                    elif "quilt" in lower_raw:
                        active_loader = "quilt"
                    else:
                        active_loader = "fabric"
                    facets = f'[["versions:{target_version}"],["categories:{active_loader}"]]'
                    url = f"https://api.modrinth.com/v2/search?limit=15&offset={offset}&facets={urllib.parse.quote(facets)}"
                elif search_type == "modpack":
                    # FIX: Worlds tab - Modrinth doesn't have 'world' type, query modpacks with map/adventure categories
                    facets = f'[["project_type:modpack"],["categories:adventure","categories:maps"]]'
                    url = f"https://api.modrinth.com/v2/search?limit=15&offset={offset}&facets={urllib.parse.quote(facets)}"
                elif search_type == "shader":
                    # Shaders - query shader project type
                    facets = f'[["project_type:shader"],["versions:{target_version}"]]'
                    url = f"https://api.modrinth.com/v2/search?limit=15&offset={offset}&facets={urllib.parse.quote(facets)}"

                if query:
                    url += f"&query={urllib.parse.quote(query)}"
                else:
                    url += "&index=downloads"
                resp = requests.get(url, headers={"User-Agent": "DragoLauncher/2.0"}).json()
                self.after(0, clear_widgets)
                hits = resp.get("hits", [])
                total_hits = resp.get("total_hits", 0)
                if not hits:
                    show_status(f"No {label_prefix} found for MC {target_version}.")
                    return
                from PIL import Image
                import io, concurrent.futures
                def fetch_icon(m):
                    m['pil_image'] = None
                    # FIX: Shader images - use icon_url with fallback to featured_gallery
                    img_url = m.get('icon_url')
                    if not img_url and m.get('featured_gallery'):
                        # featured_gallery can be a list or string
                        gallery = m['featured_gallery']
                        if isinstance(gallery, list) and len(gallery) > 0:
                            img_url = gallery[0]
                        elif isinstance(gallery, str):
                            img_url = gallery
                    if img_url:
                        try:
                            d = requests.get(img_url, timeout=3).content
                            m['pil_image'] = Image.open(io.BytesIO(d)).resize((50,50), Image.LANCZOS)
                        except: pass
                    return m
                with concurrent.futures.ThreadPoolExecutor(max_workers=15) as ex:
                    list(ex.map(fetch_icon, hits))
                self.after(0, lambda: self._render_modrinth_results(
                    hits, target_version, offset, total_hits, query,
                    results_frame, detail_frame, search_frame,
                    getattr(self, f"{prefix}version_label"), getattr(self, f"{prefix}loader_warning"),
                    search_type, search_entry, label_prefix, no_found_msg, do_search))
            except Exception as e:
                self.after(0, clear_widgets)
                show_status(f"Error: {e}")

        search_btn.configure(command=lambda: threading.Thread(target=do_search).start())
        threading.Thread(target=do_search, args=("",), daemon=True).start()

    def _render_modrinth_results(self, hits, target_version, offset, total_hits, query,
                                  results_frame, detail_frame, search_frame,
                                  version_label, loader_warning,
                                  search_type, search_entry, label_prefix, no_found_msg, do_search):
        # FIX: Add padding at bottom to prevent cards clipping through boundary
        for i, mod in enumerate(hits):
            # FIX: Rigid card structure with flex layout to prevent button misalignment
            card = ctk.CTkFrame(results_frame, fg_color="#2b2b2b", corner_radius=5, height=80)
            card.grid(row=i, column=0, sticky="ew", pady=5, padx=5)
            card.grid_columnconfigure(1, weight=1)
            card.grid_propagate(False)  # Maintain fixed height
            
            if mod.get('pil_image'):
                ctk_img = ctk.CTkImage(light_image=mod['pil_image'], size=(50, 50))
                img_w = ctk.CTkLabel(card, image=ctk_img, text="")
            else:
                img_w = ctk.CTkLabel(card, text="[Icon]", width=50, height=50, fg_color="#1e1e1e", corner_radius=5)
            img_w.grid(row=0, column=0, rowspan=2, padx=10, pady=10, sticky="n")
            
            # Title
            ctk.CTkLabel(card, text=mod["title"], font=ctk.CTkFont(weight="bold"), anchor="w").grid(row=0, column=1, sticky="w", padx=10, pady=(10,2))
            
            # FIX: Description text clamping to 2 lines equivalent (limit to ~80 chars for uniformity)
            desc_text = mod["description"][:80] + ("..." if len(mod["description"]) > 80 else "")
            ctk.CTkLabel(card, text=desc_text, text_color="#aaaaaa", anchor="w", wraplength=350).grid(row=1, column=1, sticky="nw", padx=10, pady=(2,10))
            
            ctk.CTkButton(card, text="View Info", width=70, fg_color="#8e44ad",
                         command=lambda m=mod: self._show_mod_detail(
                             m, target_version, results_frame, detail_frame, search_frame,
                             version_label, loader_warning, search_type)).grid(row=0, column=2, rowspan=2, padx=5, pady=10)
            
            install_text = "Install" if search_type == "mod" else "Install" if search_type == "shader" else "Install"
            btn = ctk.CTkButton(card, text=install_text, width=70, fg_color="#1f538d", hover_color="#2980b9")
            btn.configure(command=lambda m_id=mod["project_id"], m_title=mod["title"], b=btn:
                threading.Thread(target=self.install_modrinth_mod, args=(m_id, target_version, m_title, b)).start())
            btn.grid(row=0, column=3, rowspan=2, padx=10, pady=10)

        # FIX: Add bottom padding frame to prevent clipping
        padding_frame = ctk.CTkFrame(results_frame, fg_color="transparent", height=20)
        padding_frame.grid(row=len(hits), column=0, sticky="ew")

        pag = ctk.CTkFrame(results_frame, fg_color="transparent")
        pag.grid(row=len(hits)+1, column=0, pady=15)
        if offset > 0:
            ctk.CTkButton(pag, text="< Previous", width=100,
                         command=lambda: threading.Thread(target=do_search, args=(query, max(0, offset-15))).start()).pack(side="left", padx=10)
        if offset + 15 < total_hits:
            ctk.CTkButton(pag, text="Next >", width=100,
                         command=lambda: threading.Thread(target=do_search, args=(query, offset+15)).start()).pack(side="left", padx=10)

    def _show_mod_detail(self, mod, target_version, results_frame, detail_frame,
                          search_frame, version_label, loader_warning, search_type):
        version_label.grid_forget()
        search_frame.grid_forget()
        results_frame.grid_forget()
        for w in detail_frame.winfo_children():
            w.destroy()
        detail_frame.grid(row=0, column=0, rowspan=3, sticky="nsew", pady=5)

        def go_back():
            detail_frame.grid_forget()
            version_label.grid(row=0, column=0, sticky="w", padx=5, pady=(5,0))
            search_frame.grid(row=1, column=0, sticky="ew", pady=5)
            results_frame.grid(row=2, column=0, sticky="nsew", pady=5)

        ctk.CTkButton(detail_frame, text="← Back", width=100, fg_color="#555555",
                     command=go_back).grid(row=0, column=0, sticky="w", padx=10, pady=10)

        hf = ctk.CTkFrame(detail_frame, fg_color="transparent")
        hf.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        if mod.get('pil_image'):
            ctk_img = ctk.CTkImage(light_image=mod['pil_image'], size=(80,80))
            ctk.CTkLabel(hf, image=ctk_img, text="").grid(row=0, column=0, rowspan=2, padx=(0,20))
        else:
            ctk.CTkLabel(hf, text="[Icon]", width=80, height=80, fg_color="#1e1e1e", corner_radius=5).grid(row=0, column=0, rowspan=2, padx=(0,20))
        ctk.CTkLabel(hf, text=mod["title"], font=ctk.CTkFont(size=24, weight="bold")).grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(hf, text=f"Author: {mod.get('author', 'Unknown')}", text_color="#aaaaaa").grid(row=1, column=1, sticky="nw")
        install_btn = ctk.CTkButton(hf, text="Install", fg_color="#27ae60", font=ctk.CTkFont(weight="bold"))
        install_btn.configure(command=lambda b=install_btn:
            threading.Thread(target=self.install_modrinth_mod, args=(mod["project_id"], target_version, mod["title"], b)).start())
        install_btn.grid(row=0, column=2, rowspan=2, padx=20, sticky="e")
        hf.grid_columnconfigure(1, weight=1)

        df = ctk.CTkFrame(detail_frame, fg_color="#2b2b2b")
        df.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
        detail_frame.grid_rowconfigure(2, weight=1)
        detail_frame.grid_columnconfigure(0, weight=1)

        tb = ctk.CTkTextbox(df, wrap="word", font=ctk.CTkFont(size=14))
        tb.pack(padx=20, pady=20, fill="both", expand=True)
        tb.insert("0.0", mod["description"] + "\n\nFetching details...")
        tb.configure(state="disabled")

        def fetch():
            try:
                resp = requests.get(f"https://api.modrinth.com/v2/project/{mod['project_id']}",
                                   headers={"User-Agent": "DragoLauncher/2.0"}, timeout=5).json()
                body = resp.get("body", "")
                if body:
                    import re
                    body = re.sub(r'<[^>]+>', '', body)
                    body = re.sub(r'!\[.*?\]\([^)]+\)', '', body)
                    body = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', body)
                    if len(body) > 12000:
                        body = body[:12000] + "..."
                    self.after(0, lambda: (tb.configure(state="normal"), tb.delete("0.0","end"),
                                          tb.insert("0.0", body), tb.configure(state="disabled")))
            except: pass
        threading.Thread(target=fetch, daemon=True).start()

    def load_installed_content(self):
        for widget in self.installed_scroll.winfo_children():
            widget.destroy()

        # Check if using global .minecraft
        use_global = self.config.get("use_global_minecraft", False)

        if use_global:
            mine_dir = self._get_global_minecraft_dir()
            ctk.CTkLabel(self.installed_scroll, text="Content for: Global .minecraft",
                        font=ctk.CTkFont(size=14, weight="bold"), text_color="#3498db").grid(row=0, column=0, sticky="w", padx=5, pady=(5, 15))

            from pathlib import Path
            mods_dir = Path(mine_dir) / "mods"
            saves_dir = Path(mine_dir) / "saves"
        else:
            current_instance_id = self.config.get("current_instance")
            if not current_instance_id:
                ctk.CTkLabel(self.installed_scroll, text="No instance selected", text_color="#e74c3c").grid(row=0, column=0, pady=20)
                return

            instance = self.instance_manager.get_instance(current_instance_id)
            if not instance:
                ctk.CTkLabel(self.installed_scroll, text="Instance not found", text_color="#e74c3c").grid(row=0, column=0, pady=20)
                return

            ctk.CTkLabel(self.installed_scroll, text=f"Content for: {instance['name']}",
                        font=ctk.CTkFont(size=14, weight="bold"), text_color="#3498db").grid(row=0, column=0, sticky="w", padx=5, pady=(5, 15))

            instance_path = self.instance_manager.get_instance_path(current_instance_id)
            mods_dir = instance_path / "mods"
            saves_dir = instance_path / "saves"

        row_idx = 1
        import shutil

        # Drop zone for installing mods
        drop_frame = ctk.CTkFrame(self.installed_scroll, fg_color="#1a1a2e", corner_radius=8, border_width=2, border_color="#3498db")
        drop_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10), padx=5)

        dnd_hint = "" if not _HAVE_DND else "\n(Drag & drop files from your file manager)"
        drop_label = ctk.CTkLabel(drop_frame, text=f"📁 Click to browse .jar mods{dnd_hint}",
                                  font=ctk.CTkFont(size=12), text_color="#888888")
        drop_label.pack(pady=10)

        def browse_and_install_mod():
            from tkinter import filedialog
            files = filedialog.askopenfilenames(
                title="Select Mods to Install",
                filetypes=[("Minecraft Mods", "*.jar"), ("All Files", "*.*")]
            )
            if not files:
                return
            for fpath in files:
                try:
                    dest = mods_dir / os.path.basename(fpath)
                    os.makedirs(mods_dir, exist_ok=True)
                    shutil.copy2(fpath, dest)
                except Exception as e:
                    print(f"Error installing mod: {e}")
            self.load_installed_content()
            self._update_ui_status(f"Installed {len(files)} mod(s)", "#27ae60")

        def install_dropped_files(file_paths):
            if isinstance(file_paths, str):
                file_paths = file_paths.split()
            count = 0
            for fpath in file_paths:
                fpath = fpath.strip().strip("{}")
                if not fpath or not os.path.isfile(fpath):
                    continue
                if not fpath.lower().endswith(".jar"):
                    continue
                try:
                    dest = mods_dir / os.path.basename(fpath)
                    os.makedirs(mods_dir, exist_ok=True)
                    shutil.copy2(fpath, dest)
                    count += 1
                except Exception as e:
                    print(f"Error installing dropped mod: {e}")
            self.load_installed_content()
            if count > 0:
                self._update_ui_status(f"Installed {count} mod(s) from drag-and-drop", "#27ae60")

        drop_frame.configure(cursor="hand2")
        drop_frame.bind("<Button-1>", lambda e: browse_and_install_mod())
        drop_label.bind("<Button-1>", lambda e: browse_and_install_mod())

        # Register OS drag-and-drop if tkinterdnd2 is available
        if _HAVE_DND:
            try:
                TkinterDnD.tkdnd_init(self)
                drop_frame.drop_target_register(TkinterDnD.DND_FILES)
                drop_frame.dnd_bind("<<Drop>>", lambda e: install_dropped_files(e.data))
                drop_label.drop_target_register(TkinterDnD.DND_FILES)
                drop_label.dnd_bind("<<Drop>>", lambda e: install_dropped_files(e.data))
            except Exception:
                pass

        def create_item(parent, base_dir, filename, idx):
            item_frame = ctk.CTkFrame(parent, fg_color="#2b2b2b", corner_radius=5)
            item_frame.grid(row=idx, column=0, sticky="ew", pady=3, padx=5)
            item_frame.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(item_frame, text=filename, font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", padx=10, pady=5)

            def delete_item():
                target = base_dir / filename
                try:
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink()
                    item_frame.destroy()
                except Exception as e:
                    print(f"Delete Error: {e}")

            del_btn = ctk.CTkButton(item_frame, text="Delete", width=60, fg_color="#c0392b", hover_color="#e74c3c", command=delete_item)
            del_btn.grid(row=0, column=1, padx=10, pady=5)

        # Draw Mods
        if mods_dir.exists() and list(mods_dir.iterdir()):
            ctk.CTkLabel(self.installed_scroll, text="Installed Mods", text_color="#3498db", font=ctk.CTkFont(weight="bold", size=16)).grid(row=row_idx, column=0, sticky="w", padx=5, pady=(10, 5))
            row_idx += 1
            for f in mods_dir.iterdir():
                if f.suffix == ".jar":
                    create_item(self.installed_scroll, mods_dir, f.name, row_idx)
                    row_idx += 1

        # Draw Worlds
        if saves_dir.exists() and list(saves_dir.iterdir()):
            ctk.CTkLabel(self.installed_scroll, text="Installed Worlds", text_color="#2ecc71", font=ctk.CTkFont(weight="bold", size=16)).grid(row=row_idx, column=0, sticky="w", padx=5, pady=(20, 5))
            row_idx += 1
            for f in saves_dir.iterdir():
                if f.is_dir():
                    create_item(self.installed_scroll, saves_dir, f.name, row_idx)
                    row_idx += 1

    def _get_mods_dir(self):
        use_global = self.config.get("use_global_minecraft", False)
        if use_global:
            return Path(self._get_global_minecraft_dir()) / "mods"
        current_id = self.config.get("current_instance")
        if current_id:
            ipath = self.instance_manager.get_instance_path(current_id)
            if ipath:
                return ipath / "mods"
        return None

    def _scan_mod_conflicts(self):
        self._update_ui_status("Scanning for mod conflicts...", "#f39c12")
        mods_dir = self._get_mods_dir()
        if not mods_dir or not mods_dir.exists():
            self.after(0, lambda: self._update_ui_status("No mods directory found", "#e74c3c"))
            return
        results = scan_mods_directory(str(mods_dir))
        if results:
            self.after(0, lambda: self._show_conflict_results(results))
        else:
            self.after(0, lambda: self._update_ui_status("No conflicts found ✓", "#27ae60"))

    def _show_conflict_results(self, results):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Mod Conflict Scanner")
        dialog.geometry("700x500")
        dialog.transient(self)
        dialog.grab_set()

        scroll = ctk.CTkScrollableFrame(dialog, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(scroll, text="Scan Results", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(0, 15))

        by_severity = {"critical": [], "error": [], "warning": [], "info": []}
        for r in results:
            by_severity.setdefault(r.get("severity", "info"), []).append(r)

        severity_colors = {"critical": "#e74c3c", "error": "#e67e22", "warning": "#f1c40f", "info": "#3498db"}
        severity_labels = {"critical": "Critical", "error": "Error", "warning": "Warning", "info": "Info"}

        has_any = False
        for sev in ("critical", "error", "warning", "info"):
            items = by_severity.get(sev, [])
            if not items:
                continue
            has_any = True
            ctk.CTkLabel(scroll, text=f"{severity_labels[sev]} ({len(items)})",
                        font=ctk.CTkFont(weight="bold", size=14),
                        text_color=severity_colors[sev]).pack(anchor="w", pady=(10, 5))
            for r2 in items:
                card = ctk.CTkFrame(scroll, fg_color="#2b2b2b", corner_radius=5)
                card.pack(fill="x", pady=3, padx=5)
                ctk.CTkLabel(card, text=r2.get("file", "Unknown"), font=ctk.CTkFont(weight="bold"),
                            anchor="w").pack(fill="x", padx=10, pady=(5, 0), anchor="w")
                ctk.CTkLabel(card, text=r2["message"], text_color="#aaaaaa", wraplength=600,
                            anchor="w").pack(fill="x", padx=10, pady=(0, 5), anchor="w")

        if not has_any:
            ctk.CTkLabel(scroll, text="No issues found!", text_color="#27ae60",
                        font=ctk.CTkFont(size=14)).pack(pady=20)

        ctk.CTkButton(dialog, text="Close", fg_color="#555555",
                     command=dialog.destroy).pack(pady=10)

    def _show_crash_reports(self):
        self._update_ui_status("Checking crash reports...", "#f39c12")
        use_global = self.config.get("use_global_minecraft", False)

        if use_global:
            instance_dir = self._get_global_minecraft_dir()
        else:
            current_id = self.config.get("current_instance")
            if not current_id:
                self.after(0, lambda: self._update_ui_status("No instance selected", "#e74c3c"))
                return
            ipath = self.instance_manager.get_instance_path(current_id)
            if not ipath:
                self.after(0, lambda: self._update_ui_status("Instance not found", "#e74c3c"))
                return
            instance_dir = str(ipath)

        analyses = analyze_crash_reports(instance_dir)
        if not analyses:
            self.after(0, lambda: self._show_no_crash_reports())
        else:
            self.after(0, lambda: self._show_crash_analysis(analyses))

    def _show_no_crash_reports(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Crash Reports")
        dialog.geometry("400x200")
        dialog.transient(self)
        dialog.grab_set()
        ctk.CTkLabel(dialog, text="No crash reports found", font=ctk.CTkFont(size=16),
                    text_color="#27ae60").pack(pady=40)
        ctk.CTkLabel(dialog, text="Your game hasn't crashed recently ✓",
                    text_color="#aaaaaa").pack()
        ctk.CTkButton(dialog, text="Close", fg_color="#555555",
                     command=dialog.destroy).pack(pady=20)

    def _show_crash_analysis(self, analyses):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Crash Report Analysis")
        dialog.geometry("750x600")
        dialog.transient(self)
        dialog.grab_set()

        scroll = ctk.CTkScrollableFrame(dialog, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(scroll, text=f"Crash Reports ({len(analyses)})",
                    font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(0, 15))

        for report in analyses:
            report_frame = ctk.CTkFrame(scroll, fg_color="#2b2b2b", corner_radius=8)
            report_frame.pack(fill="x", pady=10, padx=5)

            header = ctk.CTkFrame(report_frame, fg_color="transparent")
            header.pack(fill="x", padx=10, pady=(10, 5))
            ctk.CTkLabel(header, text=report["filename"], font=ctk.CTkFont(weight="bold", size=14),
                        anchor="w").pack(side="left")
            if report.get("time"):
                ctk.CTkLabel(header, text=report["time"], text_color="#aaaaaa",
                            font=ctk.CTkFont(size=11)).pack(side="right")

            info_text = ""
            if report.get("minecraft_version"):
                info_text += f"MC: {report['minecraft_version']}  "
            if report.get("java_version"):
                info_text += f"Java: {report['java_version']}  "
            if report.get("mods_loaded"):
                info_text += f"Mods: {report['mods_loaded']}"
            if info_text:
                ctk.CTkLabel(report_frame, text=info_text, text_color="#aaaaaa",
                            font=ctk.CTkFont(size=11)).pack(anchor="w", padx=10)

            for match in report["matches"]:
                match_frame = ctk.CTkFrame(report_frame, fg_color="#1e1e1e", corner_radius=5)
                match_frame.pack(fill="x", padx=10, pady=5)

                severity_colors = {"critical": "#e74c3c", "error": "#e67e22", "warning": "#f1c40f", "info": "#3498db"}
                sev_color = severity_colors.get(match.get("severity", "info"), "#aaaaaa")

                ctk.CTkLabel(match_frame, text=f"[{match.get('severity', 'info').upper()}] {match['title']}",
                            text_color=sev_color, font=ctk.CTkFont(weight="bold", size=12)).pack(anchor="w", padx=10, pady=(5, 0))

                if match.get("suggestion"):
                    ctk.CTkLabel(match_frame, text=f"💡 {match['suggestion']}",
                                text_color="#aaaaaa", wraplength=600, justify="left",
                                font=ctk.CTkFont(size=11)).pack(anchor="w", padx=10, pady=(0, 5))

        ctk.CTkButton(dialog, text="Close", fg_color="#555555",
                     command=dialog.destroy).pack(pady=10)

    def load_visual_skin(self):
        """Load and display the current skin preview"""
        try:
            from PIL import Image
            username = self.username_entry.get().strip() or "DRAGO"
            target_path = os.path.join(self._get_global_minecraft_dir(), "CustomSkinLoader", "LocalSkin", "skins", f"{username}.png")
            
            if os.path.exists(target_path):
                img = Image.open(target_path)
                # Crop just the face (8, 8, 16, 16) for Minecraft 64x64 skins
                face = img.crop((8, 8, 16, 16))
                
                # Resize so it looks pixel-perfect
                face = face.resize((128, 128), resample=Image.NEAREST)
                ctk_img = ctk.CTkImage(light_image=face, size=(128,128))
                
                self.skin_preview_label.configure(image=ctk_img, text="")
                # Keep reference to prevent garbage collection
                self.skin_preview_label.image = ctk_img
            else:
                # No skin found - show default message
                self.skin_preview_label.configure(image=None, text=f"No skin found for '{username}'\n\n👆 Upload a skin or browse below")
        except Exception as e:
            print(f"Error loading skin preview: {e}")
            self.skin_preview_label.configure(image=None, text="Unable to load skin preview")

    def search_modrinth(self, init_query=None, offset=0):
        # Clear old results safely via the main thread context
        def clear_widgets():
            for widget in self.mod_results_frame.winfo_children():
                widget.destroy()
        self.after(0, clear_widgets)
            
        import requests
        import urllib.parse
        import re
        
        # Determine query string
        query = self.mod_search_entry.get().strip() if init_query is None else init_query
        
        display_version = self.version_var.get()
        # Get actual version ID from display name
        raw_version = self.version_id_to_display.get(display_version, display_version)
        target_version = "1.20.1" # Fallback
        
        # Extract pure Minecraft version from various formats
        # Try to read from version JSON if it's a modded version
        mine_dir = self._get_global_minecraft_dir()
        version_json_path = os.path.join(mine_dir, "versions", raw_version, f"{raw_version}.json")
        
        if os.path.exists(version_json_path):
            try:
                with open(version_json_path, 'r') as f:
                    version_data = json.load(f)
                    # Check for inheritsFrom field (Fabric/Forge versions)
                    if 'inheritsFrom' in version_data:
                        target_version = version_data['inheritsFrom']
                        print(f"DEBUG: Found inheritsFrom: {target_version}")
                    elif 'id' in version_data:
                        # Try to extract from id
                        version_id = version_data['id']
                        if re.match(r'^\d+\.\d+(?:\.\d+)?$', version_id):
                            target_version = version_id
            except Exception as e:
                print(f"DEBUG: Error reading version JSON: {e}")
        
        # Fallback: Try to extract from version string
        if target_version == "1.20.1":  # Still default, try parsing
            if "-" in raw_version:
                # For fabric-loader-X.X.X-1.20.1 format, take the last part
                parts = raw_version.split("-")
                for part in reversed(parts):
                    if re.match(r'^\d+\.\d+(?:\.\d+)?$', part):
                        target_version = part
                        break
            elif re.match(r'^\d+\.\d+(?:\.\d+)?$', raw_version):
                target_version = raw_version
        
        print(f"DEBUG: Raw version: {raw_version}, Extracted MC version: {target_version}")
        
        # Check if vanilla version (no mod loader)
        lower_raw = raw_version.lower()
        is_vanilla = not any(loader in lower_raw for loader in ['fabric', 'forge', 'quilt', 'neoforge'])
        
        # Determine active loader
        if "forge" in lower_raw and "neoforge" not in lower_raw:
            active_loader = "forge"
        elif "neoforge" in lower_raw:
            active_loader = "neoforge"
        elif "quilt" in lower_raw:
            active_loader = "quilt"
        else:
            active_loader = "fabric"  # Default to fabric, even for vanilla (we can install it)
        
        # Update version label and warning
        self.after(0, lambda: self.mod_version_label.configure(text=f"Browsing {active_loader.capitalize()} mods for: Minecraft {target_version} (Page {offset//15 + 1})"))
        
        if is_vanilla:
            self.after(0, lambda: self.mod_loader_warning.configure(
                text=f"⚠️ Vanilla version - Install {active_loader.capitalize()} to use mods!",
                text_color="#e74c3c"
            ))
        else:
            self.after(0, lambda: self.mod_loader_warning.configure(text="✓ Mod loader detected", text_color="#27ae60"))
            
        def show_status(txt):
            self.after(0, lambda: ctk.CTkLabel(self.mod_results_frame, text=txt).grid(row=0, column=0, pady=20))
            
        show_status(f"Fetching Modrinth for Minecraft {target_version} ({active_loader.capitalize()})...")
        
        try:
            # Setup specific query to Modrinth - Filter by dynamic loader and selected Version
            facets = f'[["versions:{target_version}"],["categories:{active_loader}"]]'
            encoded_facets = urllib.parse.quote(facets)
            url = f"https://api.modrinth.com/v2/search?limit=15&offset={offset}&facets={encoded_facets}"
            if query:
                url += f"&query={urllib.parse.quote(query)}"
            else:
                url += "&index=downloads" # Fetch trending if blank search
                
            headers = {"User-Agent": "DragoLauncher/1.0"}
            resp = requests.get(url, headers=headers).json()
            
            self.after(0, clear_widgets)
                
            hits = resp.get("hits", [])
            total_hits = resp.get("total_hits", 0)
            if not hits:
                show_status(f"No {active_loader.capitalize()} mods found for Minecraft {target_version}.")
                return
            
            # Prefetch icons in background thread to avoid freezing UI
            from PIL import Image
            import io
            import concurrent.futures
            
            def fetch_icon(mod_item):
                mod_item['pil_image'] = None
                if mod_item.get('icon_url'):
                    try:
                        img_data = requests.get(mod_item['icon_url'], timeout=3).content
                        mod_item['pil_image'] = Image.open(io.BytesIO(img_data)).resize((50, 50), Image.LANCZOS)
                    except Exception:
                        pass
                return mod_item

            with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
                list(executor.map(fetch_icon, hits))
                
            # Safely render results onto UI
            self.after(0, self.render_mod_results, hits, target_version, offset, total_hits, query)
                
        except Exception as e:
            self.after(0, clear_widgets)
            show_status(f"Error connecting to Modrinth:\n{e}")

    def render_mod_results(self, hits, target_version, offset, total_hits, query):
        for i, mod in enumerate(hits):
            card = ctk.CTkFrame(self.mod_results_frame, fg_color="#2b2b2b", corner_radius=5)
            card.grid(row=i, column=0, sticky="ew", pady=5, padx=5)
            card.grid_columnconfigure(1, weight=1) # text column
            
            if mod.get('pil_image'):
                ctk_img = ctk.CTkImage(light_image=mod['pil_image'], size=(50, 50))
                img_widget = ctk.CTkLabel(card, image=ctk_img, text="")
            else:
                img_widget = ctk.CTkLabel(card, text="📦", font=ctk.CTkFont(size=24), width=50, height=50, fg_color="#1e1e1e", corner_radius=5)
            
            img_widget.grid(row=0, column=0, rowspan=2, padx=10, pady=10)
            
            ctk.CTkLabel(card, text=mod["title"], font=ctk.CTkFont(weight="bold")).grid(row=0, column=1, sticky="w", padx=10, pady=(5,0))
            ctk.CTkLabel(card, text=mod["description"][:100]+"...", text_color="#aaaaaa").grid(row=1, column=1, sticky="w", padx=10, pady=(0,5))
            
            view_btn = ctk.CTkButton(card, text="View Info", width=70, fg_color="#8e44ad", hover_color="#9b59b6",
                                     command=lambda m=mod: self.show_mod_details(m, target_version))
            view_btn.grid(row=0, column=2, rowspan=2, padx=5, pady=10)
            
            btn = ctk.CTkButton(card, text="Install\nMod", width=70, fg_color="#1f538d", hover_color="#2980b9")
            btn.configure(command=lambda m_id=mod["project_id"], m_title=mod["title"], b=btn: threading.Thread(target=self.install_modrinth_mod, args=(m_id, target_version, m_title, b)).start())
            btn.grid(row=0, column=3, rowspan=2, padx=10, pady=10)

        # Build Pagination Framework
        pagination_frame = ctk.CTkFrame(self.mod_results_frame, fg_color="transparent")
        pagination_frame.grid(row=len(hits), column=0, pady=15)
        
        if offset > 0:
            prev_btn = ctk.CTkButton(pagination_frame, text="< Previous", width=100,
                                     command=lambda: threading.Thread(target=self.search_modrinth, args=(query, max(0, offset - 15))).start())
            prev_btn.pack(side="left", padx=10)
            
        if offset + 15 < total_hits:
            next_btn = ctk.CTkButton(pagination_frame, text="Next >", width=100,
                                     command=lambda: threading.Thread(target=self.search_modrinth, args=(query, offset + 15)).start())
            next_btn.pack(side="left", padx=10)

    def show_mod_details(self, mod, target_version):
        self.mod_version_label.grid_forget()
        self.search_frame.grid_forget()
        self.mod_results_frame.grid_forget()
        
        for widget in self.mod_detail_frame.winfo_children():
            widget.destroy()
            
        self.mod_detail_frame.grid(row=0, column=0, rowspan=3, sticky="nsew", pady=5)
        
        def go_back():
            self.mod_detail_frame.grid_forget()
            self.mod_version_label.grid(row=0, column=0, sticky="w", padx=5, pady=(5, 0))
            self.search_frame.grid(row=1, column=0, sticky="ew", pady=5)
            self.mod_results_frame.grid(row=2, column=0, sticky="nsew", pady=5)
            
        back_btn = ctk.CTkButton(self.mod_detail_frame, text="← Back to Search", width=120, fg_color="#555555", hover_color="#444444", command=go_back)
        back_btn.grid(row=0, column=0, sticky="w", padx=10, pady=10)
        
        header_frame = ctk.CTkFrame(self.mod_detail_frame, fg_color="transparent")
        header_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        
        if mod.get('pil_image'):
            ctk_img = ctk.CTkImage(light_image=mod['pil_image'], size=(80, 80))
            img_widget = ctk.CTkLabel(header_frame, image=ctk_img, text="")
        else:
            img_widget = ctk.CTkLabel(header_frame, text="📦", font=ctk.CTkFont(size=36), width=80, height=80, fg_color="#1e1e1e", corner_radius=5)
        img_widget.grid(row=0, column=0, rowspan=2, padx=(0, 20))
        
        ctk.CTkLabel(header_frame, text=mod["title"], font=ctk.CTkFont(size=24, weight="bold")).grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(header_frame, text=f"Author: {mod.get('author', 'Unknown')}", text_color="#aaaaaa").grid(row=1, column=1, sticky="nw")
        
        install_btn = ctk.CTkButton(header_frame, text="Install Mod", fg_color="#27ae60", hover_color="#2ecc71", font=ctk.CTkFont(weight="bold"))
        install_btn.configure(command=lambda b=install_btn: threading.Thread(target=self.install_modrinth_mod, args=(mod["project_id"], target_version, mod["title"], b)).start())
        install_btn.grid(row=0, column=2, rowspan=2, padx=20, sticky="e")
        header_frame.grid_columnconfigure(1, weight=1)
        
        desc_frame = ctk.CTkFrame(self.mod_detail_frame, fg_color="#2b2b2b")
        desc_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
        self.mod_detail_frame.grid_rowconfigure(2, weight=1)
        self.mod_detail_frame.grid_columnconfigure(0, weight=1)
        
        desc_textbox = ctk.CTkTextbox(desc_frame, wrap="word", font=ctk.CTkFont(size=14))
        desc_textbox.pack(padx=20, pady=20, fill="both", expand=True)
        desc_textbox.insert("0.0", mod["description"] + "\n\nFetching complete description...")
        desc_textbox.configure(state="disabled")

        def fetch_full_info():
            import requests
            import re
            from PIL import Image, ImageTk
            import io
            try:
                # Query the specific project endpoint to get the giant "body" description
                resp = requests.get(f"https://api.modrinth.com/v2/project/{mod['project_id']}", headers={"User-Agent": "DragoLauncher/1.0"}, timeout=5).json()
                body = resp.get("body", "")
                if body:
                    # Extract image URLs to render them natively (limit to 10 to protect memory)
                    img_urls = [url for _, url in re.findall(r'!\[(.*?)\]\(([^)]+)\)', body)][:10]
                    
                    # Clean up html and basic markdown headers so it reads cleaner in a UI label
                    body = re.sub(r'<[^>]+>', '', body)
                    body = re.sub(r'#+\s+', '', body)
                    # Strip markdown images entirely from text flow
                    body = re.sub(r'!\[.*?\]\([^)]+\)', '', body)
                    # Convert markdown links to just their text
                    body = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', body)
                    
                    # Limit the string size so Tkinter doesn't freeze on gigantic mod pages
                    if len(body) > 12000:
                        body = body[:12000] + "...\n\n[Description Truncated due to length - Install to play!]"
                    
                    def update_ui(text=body):
                        desc_textbox.configure(state="normal")
                        desc_textbox.delete("0.0", "end")
                        desc_textbox.insert("0.0", text)
                        desc_textbox.configure(state="disabled")

                    self.after(0, update_ui)
                    
                    # Async load and render the images at the bottom of the textbox
                    if img_urls:
                        desc_textbox.image_references = getattr(desc_textbox, 'image_references', [])
                        
                        def inject_images():
                            for url in img_urls:
                                try:
                                    # Ignore svg shields and badges which often break or don't render well
                                    if ".svg" in url.lower() or "shields.io" in url.lower():
                                        continue
                                        
                                    img_data = requests.get(url, timeout=5).content
                                    pil_img = Image.open(io.BytesIO(img_data))
                                    
                                    # Scale down if too large for launcher panel
                                    max_w = 600
                                    if pil_img.width > max_w:
                                        ratio = max_w / float(pil_img.width)
                                        new_h = int((float(pil_img.height) * float(ratio)))
                                        pil_img = pil_img.resize((max_w, new_h), Image.LANCZOS)
                                        
                                    photo_img = ImageTk.PhotoImage(pil_img)
                                    
                                    def append_to_tb(img=photo_img):
                                        desc_textbox.image_references.append(img)
                                        desc_textbox.configure(state="normal")
                                        desc_textbox.insert("end", "\n\n")
                                        desc_textbox._textbox.image_create("end", image=img)
                                        desc_textbox.configure(state="disabled")
                                        
                                    self.after(0, append_to_tb)
                                except Exception as e:
                                    print(f"Failed to load markdown image {url}: {e}")
                                    
                        threading.Thread(target=inject_images, daemon=True).start()
            except Exception:
                pass
                
        threading.Thread(target=fetch_full_info, daemon=True).start()

    def install_modrinth_mod(self, project_id, target_version, project_title, btn=None):
        import requests
        import shutil
        from pathlib import Path

        if btn:
            self.after(0, lambda: btn.configure(text="Installing", state="disabled", fg_color="#f39c12"))
        
        # Check if current version supports mods
        display_version = self.version_var.get()
        actual_version = self.version_id_to_display.get(display_version, display_version)
        
        lower_raw = actual_version.lower()
        # Determine active loader context
        if "forge" in lower_raw and "neoforge" not in lower_raw:
            active_loader = "forge"
        elif "neoforge" in lower_raw:
            active_loader = "neoforge"
        elif "quilt" in lower_raw:
            active_loader = "quilt"
        else:
            active_loader = "fabric"  # Default fallback if vanilla
            
        # Check if it's a vanilla version (no mod loader)
        is_vanilla = not any(loader in lower_raw for loader in ['fabric', 'forge', 'quilt', 'neoforge'])
        
        if is_vanilla:
            # Offer to auto-install appropriate loader (currently only Fabric auto-install is supported)
            confirm = ctk.CTkToplevel(self)
            confirm.title("🔧 Install Mod Loader?")
            confirm.geometry("520x380")  # Increased for better spacing
            confirm.transient(self)
            confirm.grab_set()
            confirm.resizable(False, False)
            
            ctk.CTkLabel(confirm, text="🔧 Fabric Required", 
                        font=ctk.CTkFont(size=18, weight="bold"),
                        text_color="#3498db").pack(pady=20)
            
            ctk.CTkLabel(confirm, 
                        text=f"You're trying to install a mod on vanilla:\n\n'{display_version}'\n\nThis mod requires Fabric to work.",
                        wraplength=450,
                        justify="center").pack(pady=10)
            
            ctk.CTkLabel(confirm,
                        text="Would you like me to automatically:",
                        font=ctk.CTkFont(weight="bold")).pack(pady=(20, 5))
            
            ctk.CTkLabel(confirm,
                        text=f"1. Install {active_loader.capitalize()} for Minecraft {target_version}\n2. Install {project_title}\n3. Add '{active_loader.capitalize()} {target_version}' to your version list",
                        justify="left",
                        text_color="#27ae60").pack(pady=5)
            
            ctk.CTkLabel(confirm,
                        text="This will take about 30 seconds.",
                        font=ctk.CTkFont(size=11),
                        text_color="#aaaaaa").pack(pady=5)
            
            button_frame = ctk.CTkFrame(confirm, fg_color="transparent")
            button_frame.pack(pady=20)
            
            def install_loader_and_mod():
                confirm.destroy()
                threading.Thread(target=self._install_loader_then_mod, 
                               args=(target_version, project_id, project_title, active_loader, btn),
                               daemon=True).start()
            
            def cancel():
                confirm.destroy()
                self._update_ui_status("Mod installation cancelled", "#aaaaaa")
            
            ctk.CTkButton(button_frame, text=f"Yes, Install {active_loader.capitalize()} + Mod", 
                         fg_color="#27ae60", hover_color="#2ecc71",
                         command=install_loader_and_mod, width=200).pack(side="left", padx=10)
            
            ctk.CTkButton(button_frame, text="Cancel",
                         fg_color="#555555", hover_color="#444444",
                         command=cancel, width=100).pack(side="left", padx=10)
            
            return  # Wait for user decision
        
        # If already has mod loader, proceed normally
        self._download_and_install_mod(project_id, target_version, project_title, btn, active_loader)
    
    def _install_loader_then_mod(self, mc_version, mod_project_id, mod_title, active_loader="fabric", btn=None):
        """Install Fabric/Forge/etc., then install the mod"""
        try:
            self._update_ui_status(f"Installing {active_loader.capitalize()} for MC {mc_version}...", "#3498db")
            import requests
            mine_dir = self._get_global_minecraft_dir()
            
            if active_loader == "fabric":
                # Get Fabric version info
                fabric_meta_url = f"https://meta.fabricmc.net/v2/versions/loader/{mc_version}"
                headers = {"User-Agent": "DragoLauncher/2.0"}
                
                fabric_versions = requests.get(fabric_meta_url, headers=headers, timeout=10).json()
                
                if not fabric_versions:
                    self._update_ui_status(f"No Fabric available for MC {mc_version}", "#e74c3c")
                    return
                
                # Get latest stable Fabric loader
                latest_loader = fabric_versions[0]['loader']['version']
                
                self._update_ui_status(f"Downloading Fabric {latest_loader}...", "#3498db")
                
                # Install Fabric
                import minecraft_launcher_lib
                minecraft_launcher_lib.fabric.install_fabric(mc_version, mine_dir)
            elif active_loader == "forge":
                import minecraft_launcher_lib
                self._update_ui_status(f"Finding Forge for MC {mc_version}...", "#3498db")
                forge_version = minecraft_launcher_lib.forge.find_forge_version(mc_version)
                if not forge_version:
                    self._update_ui_status(f"No Forge available for MC {mc_version}", "#e74c3c")
                    return
                self._update_ui_status(f"Downloading Forge {forge_version}...", "#3498db")
                minecraft_launcher_lib.forge.install_forge_version(forge_version, mine_dir)
            elif active_loader == "neoforge":
                self._update_ui_status("NeoForge auto-install is not supported yet.", "#e74c3c")
                return
            elif active_loader == "quilt":
                import minecraft_launcher_lib
                self._update_ui_status(f"Finding Quilt for MC {mc_version}...", "#3498db")
                try:
                    minecraft_launcher_lib.quilt.install_quilt(mc_version, mine_dir)
                except AttributeError:
                    self._update_ui_status("Quilt auto-install is not supported.", "#e74c3c")
                    return
                    
            self._update_ui_status(f"✓ {active_loader.capitalize()} installed! Now installing {mod_title}...", "#27ae60")
            
            # Small delay to let user see the success message
            import time
            time.sleep(1)
            
            # Now install the mod
            self._download_and_install_mod(mod_project_id, mc_version, mod_title, btn, active_loader)
            
            # Refresh version dropdown to show new version
            self.after(0, self._refresh_version_dropdown)
            
        except Exception as e:
            self._update_ui_status(f"Failed to install {active_loader.capitalize()}: {e}", "#e74c3c")
            print(f"{active_loader.capitalize()} installation error: {e}")
            import traceback
            traceback.print_exc()
    
    def _download_and_install_mod(self, project_id, target_version, project_title, btn=None, active_loader="fabric"):
        """Download and install a mod (separated for reuse)"""
        import requests
        import shutil
        from pathlib import Path
        
        self._update_ui_status(f"Finding {project_title} for MC {target_version} ({active_loader})...", "#f1c40f")
        
        # Check if using global .minecraft or instance system
        use_global = self.config.get("use_global_minecraft", False)
        
        if use_global:
            # Use global .minecraft directory
            mine_dir = self._get_global_minecraft_dir()
            mods_dir = Path(mine_dir) / "mods"
            mods_dir.mkdir(exist_ok=True)
        else:
            # Get current instance
            current_instance_id = self.config.get("current_instance")
            if not current_instance_id:
                self._update_ui_status("No instance selected!", "#e74c3c")
                return
            
            instance_path = self.instance_manager.get_instance_path(current_instance_id)
            if not instance_path:
                self._update_ui_status("Instance not found!", "#e74c3c")
                return
            
            mods_dir = instance_path / "mods"
            mods_dir.mkdir(exist_ok=True)
        
        try:
            # Query the specific version required
            url = f"https://api.modrinth.com/v2/project/{project_id}/version?loaders=[\"{active_loader}\"]&game_versions=[\"{target_version}\"]"
            headers = {"User-Agent": "DragoLauncher/1.0"}
            resp = requests.get(url, headers=headers).json()
            
            if not resp:
                self._update_ui_status(f"No version found for MC {target_version} ({active_loader})!", "#e74c3c")
                return
                
            # Get latest matching file
            file_data = resp[0]["files"][0]
            download_url = file_data["url"]
            filename = file_data["filename"]
            
            target_path = mods_dir / filename
            
            self._update_ui_status(f"Downloading {project_title}...", "#3498db")
            
            # File download
            with requests.get(download_url, stream=True) as r:
                with open(target_path, 'wb') as f:
                    shutil.copyfileobj(r.raw, f)
            
            self._update_ui_status(f"✓ Installed {project_title} for MC {target_version}!", "#27ae60")
            
            if btn:
                self.after(0, lambda: btn.configure(text="Installed", fg_color="#27ae60"))
                
        except Exception as e:
            self._update_ui_status(f"Failed to install mod", "#e74c3c")
            if btn:
                self.after(0, lambda: btn.configure(text="Install\nFailed", fg_color="#e74c3c", state="normal"))
            print(f"Mod Install Error: {e}")
    
    def _refresh_version_dropdown(self):
        """Refresh the version dropdown to show newly installed versions"""
        try:
            mine_dir = self._get_global_minecraft_dir()
            raw_installed = minecraft_launcher_lib.utils.get_installed_versions(mine_dir)
            self.installed_versions_cache = [v['id'] for v in raw_installed]
            
            # Rebuild dropdown values with friendly names
            self.version_id_to_display = {}
            dropdown_values = []
            
            def get_friendly_name(version_id):
                version_json_path = os.path.join(mine_dir, "versions", version_id, f"{version_id}.json")
                if os.path.exists(version_json_path):
                    try:
                        with open(version_json_path, 'r') as f:
                            version_data = json.load(f)
                            if 'inheritsFrom' in version_data:
                                mc_version = version_data['inheritsFrom']
                                if 'fabric' in version_id.lower():
                                    return f"Fabric {mc_version}"
                                elif 'forge' in version_id.lower():
                                    return f"Forge {mc_version}"
                                elif 'quilt' in version_id.lower():
                                    return f"Quilt {mc_version}"
                                else:
                                    return f"Modded {mc_version}"
                    except Exception:
                        pass
                return version_id
            
            for iv in self.installed_versions_cache:
                friendly_name = get_friendly_name(iv)
                self.version_id_to_display[friendly_name] = iv
                # Ensure no duplicates
                if friendly_name not in dropdown_values:
                    dropdown_values.append(friendly_name)

            self.dropdown_values = dropdown_values
            # Append OptiFine
            self.fetch_optifine_versions()
            
            self._update_ui_status("✓ Version list updated - Fabric is now available!", "#27ae60")
            
        except Exception as e:
            print(f"Error refreshing versions: {e}")

    def _on_internet_restored(self):
        """Silently refresh content when internet comes back"""
        if hasattr(self, 'main_frame') and self.main_frame.winfo_viewable():
            threading.Thread(target=self.fetch_real_minecraft_news, daemon=True).start()
        self._update_ui_status("Connection restored", "#27ae60")

    def fetch_optifine_versions(self):
        """
        Scrapes OptiFine versions directly from optifine.net and inserts them directly
        above their vanilla equivalent.
        """
        try:
            import requests
            import re
            
            # Scrape direct from Optifine
            response = requests.get("https://optifine.net/downloads", verify=False, timeout=10)
            html = response.text
            
            # Find Optifine jar identifiers (e.g. OptiFine_1.21.11_HD_U_J9.jar)
            matches = re.findall(r'OptiFine_(\d+\.\d+(\.\d+)?)_([A-Z0-9_]+)\.jar', html)
            
            optifine_manifest = {}
            for mc_ver, _, build_id in matches:
                optifine_id = f"{mc_ver}-OptiFine_{build_id}"
                # If we haven't mapped this MC version yet, map it (gets the latest build in the list)
                if optifine_id not in optifine_manifest.values():
                    # Link to download page mirror
                    jar_filename = f"OptiFine_{mc_ver}_{build_id}.jar"
                    optifine_manifest[optifine_id] = f"https://optifine.net/downloadx?f={jar_filename}&x=1"
            
            self.optifine_manifest = optifine_manifest
            
            # Group them in the UI directly above their vanilla versions
            new_dropdown = []
            
            # Use current dropdown_values to insert OptiFine versions in the logical order
            for display_name in self.dropdown_values:
                actual_id = self.version_id_to_display.get(display_name, display_name)
                
                # If it's a vanilla release, check if we scraped an OptiFine version for it
                opti_tag = None
                for opti_id in optifine_manifest.keys():
                    if opti_id.startswith(f"{actual_id}-OptiFine"):
                        opti_tag = opti_id
                        break
                        
                if opti_tag and opti_tag not in new_dropdown:
                    new_dropdown.append(opti_tag)
                    self.version_id_to_display[opti_tag] = opti_tag

                # Add vanilla version beneath it
                if display_name not in new_dropdown:
                    new_dropdown.append(display_name)
                    
            self.dropdown_values = new_dropdown
                    
        except Exception as e:
            print(f"Failed to scrape OptiFine versions: {e}")

    def check_and_download_optifine(self, version_name, mine_dir):
        version_dir = os.path.join(mine_dir, "versions", version_name)
        
        if "OptiFine" in version_name and not os.path.exists(version_dir):
            if not hasattr(self, 'optifine_manifest'):
                self.fetch_optifine_versions()

            download_url = self.optifine_manifest.get(version_name)
            if not download_url:
                raise Exception("OptiFine download URL not found in manifest!")
                
            jar_path = os.path.join(mine_dir, f"{version_name}_Installer.jar")
            
            # --- UI Feedback (Progress Bar) ---
            self._update_ui_status(f"Downloading {version_name}...", "#3498db")
            self.progress_bar.pack(pady=10)
            self.progress_bar.set(0)
            
            import requests # Must be available globally or imported here
            # Download the JAR with progress
            response = requests.get(download_url, stream=True)
            total_size = int(response.headers.get('content-length', 0))
            block_size = 1024
            downloaded = 0
            
            with open(jar_path, 'wb') as file:
                for data in response.iter_content(block_size):
                    file.write(data)
                    downloaded += len(data)
                    if total_size > 0:
                        progress = float(downloaded) / float(total_size)
                        self.progress_bar.set(progress)
                        # Update Tkinter window
                        self.update_idletasks()
                        
            self._update_ui_status("Extracting OptiFine (Headless)...", "#f39c12")
            self.install_optifine_headless(jar_path, mine_dir, version_name)

    def install_optifine_headless(self, installer_jar_path, mine_dir, target_version_name):
        """
        Runs the OptiFine JAR invisibly, extracts the custom libraries, 
        and generates the [version].json metadata file.
        """
        import minecraft_launcher_lib
        import subprocess
        
        java_path = minecraft_launcher_lib.utils.get_java_executable()
        if not java_path:
            java_path = "java" # Fallback to system env
            
        try:
            # Run Optifine Installer dynamically in the background without GUI
            # Syntax: java -jar OptiFine.jar install <Target .minecraft Directory> 
            
            install_command = [
                java_path,
                "-jar",
                installer_jar_path,
                "install", 
                mine_dir
            ]
            
            subprocess.run(
                install_command, 
                check=True, 
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                cwd=mine_dir
            )
            
            # Cleanup the installer JAR after it generates the folder
            if os.path.exists(installer_jar_path):
                os.remove(installer_jar_path)
                
            self._update_ui_status(f"OptiFine installed successfully!", "#27ae60")
            
        except subprocess.CalledProcessError as e:
            self._update_ui_status("OptiFine extraction failed!", "#e74c3c")
            print(f"Extraction Error: {e}")

    def check_for_updates(self, silent=False):
        def _check():
            try:
                import requests
                # Replace these to match your repository exactly
                resp = requests.get("https://api.github.com/repos/GhiathBr/Drago-Launcher/releases/latest", timeout=5)
                if resp.status_code == 404:
                     return # no releases yet
                     
                latest_release = resp.json()
                latest_version = latest_release.get("tag_name", self.CURRENT_VERSION)
                
                if latest_version != self.CURRENT_VERSION and latest_version.startswith("v"):
                    # We have an update
                    self.after(0, lambda: self.prompt_for_update(latest_release))
                elif not silent:
                    self.after(0, lambda: self._update_ui_status("You are on the latest version!", "#27ae60"))
            except Exception as e:
                pass
        threading.Thread(target=_check, daemon=True).start()
        
    def prompt_for_update(self, release_data):
        import tkinter.messagebox as messagebox
        import requests
        import sys
        
        latest_version = release_data.get("tag_name")
        assets = release_data.get("assets", [])
        
        is_windows = platform.system() == "Windows"
        
        # Look for platform-appropriate asset
        asset_ext = ".exe" if is_windows else (".AppImage" if platform.system() == "Linux" else ".dmg")
        download_url = None
        for asset in assets:
            if asset["name"].endswith(asset_ext):
                download_url = asset["browser_download_url"]
                break
                
        if not download_url:
             return
             
        if messagebox.askyesno("Update Available", f"A new version ({latest_version}) is available!\nDo you want to update now?"):
            self._update_ui_status("Downloading update...", "#f39c12")
            
            def _download_and_apply():
                try:
                    new_exe_data = requests.get(download_url).content
                    update_exe_path = f"DragoLauncher_Update{asset_ext}"
                    
                    with open(update_exe_path, "wb") as f:
                        f.write(new_exe_data)
                        
                    current_exe = os.path.basename(sys.executable)
                    
                    if not getattr(sys, 'frozen', False):
                         self.after(0, lambda: self._update_ui_status("Can't auto-update python scripts.", "#e74c3c"))
                         return
                    
                    if is_windows:
                        bat_path = "updater.bat"
                        with open(bat_path, "w") as f:
                            f.write(f'''@echo off
timeout /t 2 /nobreak >nul
del "{current_exe}"
rename "DragoLauncher_Update.exe" "{current_exe}"
start "" "{current_exe}"
del "%~f0"
''')
                        import subprocess
                        startupinfo = None
                        if os.name == 'nt':
                            startupinfo = subprocess.STARTUPINFO()
                            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        subprocess.Popen(
                            bat_path, shell=True,
                            startupinfo=startupinfo,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                        )
                        self.after(0, self.destroy)
                    else:
                        shell_path = "/tmp/drago_updater.sh"
                        with open(shell_path, "w") as f:
                            f.write(f'''#!/bin/sh
sleep 2
mv "{update_exe_path}" "{current_exe}"
chmod +x "{current_exe}"
exec "{current_exe}"
''')
                        os.chmod(shell_path, 0o755)
                        subprocess.Popen(["/bin/sh", shell_path])
                        self.after(0, self.destroy)
                except Exception as e:
                    self.after(0, lambda: self._update_ui_status("Update failed!", "#e74c3c"))
            threading.Thread(target=_download_and_apply, daemon=True).start()

    def open_settings(self):
        settings_window = ctk.CTkToplevel(self)
        settings_window.title("Settings")
        settings_window.geometry("500x700")
        settings_window.transient(self)
        settings_window.resizable(False, False)

        # Use scrollable frame for all content
        scroll = ctk.CTkScrollableFrame(settings_window, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(scroll, text="Launcher Settings", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(0, 15))

        # --- Theme Selection ---
        ctk.CTkLabel(scroll, text="Theme:", font=ctk.CTkFont(weight="bold")).pack(pady=(10, 0))
        theme_var = ctk.StringVar(value=self.config.get("theme", DEFAULT_THEME))
        theme_menu = ctk.CTkOptionMenu(scroll, variable=theme_var, values=get_theme_names(), width=300)
        theme_menu.pack(pady=5)

        # --- Instance Mode Toggle ---
        ctk.CTkLabel(scroll, text="Game Directory Mode:", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 5))

        use_global_var = ctk.BooleanVar(value=self.config.get("use_global_minecraft", True))

        mode_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        mode_frame.pack(pady=5)

        ctk.CTkRadioButton(mode_frame, text="Use Global .minecraft (Default)",
                          variable=use_global_var, value=True).pack(anchor="w", padx=20, pady=2)
        ctk.CTkRadioButton(mode_frame, text="Use Instance System (Advanced)",
                          variable=use_global_var, value=False).pack(anchor="w", padx=20, pady=2)

        ctk.CTkLabel(scroll, text="⚠️ Changing mode requires restart",
                    text_color="#f1c40f", font=ctk.CTkFont(size=10)).pack(pady=5)

        # Get Max RAM dynamically
        max_ram = 16
        if platform.system() == "Windows":
            try:
                import ctypes
                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                                ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
                stat = MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(stat)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
                max_ram = int(round(stat.ullTotalPhys / (1024**3)))
            except Exception:
                pass

        max_ram = max(2, max_ram)

        # Memory Slider
        ctk.CTkLabel(scroll, text=f"Default RAM (Global Mode):", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 0))
        ctk.CTkLabel(scroll, text=f"Max: {max_ram} GB", font=ctk.CTkFont(size=10), text_color="#aaaaaa").pack()

        current_mem = float(self.config.get("memory", 6))
        if current_mem > max_ram:
            current_mem = float(max_ram)

        mem_var = ctk.DoubleVar(value=current_mem)

        mem_label = ctk.CTkLabel(scroll, text=f"{int(current_mem)} GB", font=ctk.CTkFont(weight="bold"))

        def update_mem_label(val):
            mem_label.configure(text=f"{int(val)} GB")

        steps = max(1, max_ram - 2)
        mem_slider = ctk.CTkSlider(scroll, from_=2, to=max_ram, number_of_steps=steps, variable=mem_var, command=update_mem_label)
        mem_slider.pack(pady=10)
        mem_label.pack()

        # --- Launch Options ---
        ctk.CTkLabel(scroll, text="Launch Options:", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 5))
        show_console_var = ctk.BooleanVar(value=self.config.get("show_console", True))
        ctk.CTkCheckBox(scroll, text="Show Game Console on Launch", variable=show_console_var).pack(pady=2)
        auto_backup_var = ctk.BooleanVar(value=self.config.get("auto_backup", True))
        ctk.CTkCheckBox(scroll, text="Auto-backup before launching", variable=auto_backup_var).pack(pady=2)

        # --- Security ---
        ctk.CTkLabel(scroll, text="Security:", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 5))
        ssl_verify_var = ctk.BooleanVar(value=self.config.get("ssl_verify", False))
        
        # FIX: Text wrapping for long descriptions to prevent cutoff
        ssl_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        ssl_frame.pack(fill="x", pady=2, padx=20)
        ssl_frame.grid_columnconfigure(1, weight=1)
        
        ssl_cb = ctk.CTkCheckBox(ssl_frame, text="", variable=ssl_verify_var, width=24)
        ssl_cb.grid(row=0, column=0, sticky="w", padx=(0, 10))
        
        ssl_label = ctk.CTkLabel(ssl_frame, text="Enable SSL Verification (more secure, may break downloads with some antivirus)", 
                                justify="left", text_color="#dddddd", wraplength=380, anchor="w")
        ssl_label.grid(row=0, column=1, sticky="w")
        # Bind label click to toggle checkbox
        ssl_label.bind("<Button-1>", lambda e: ssl_cb.toggle())

        # --- Portable Mode ---
        ctk.CTkLabel(scroll, text="Portable Mode:", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 5))
        portable_var = ctk.BooleanVar(value=self.using_portable)
        
        port_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        port_frame.pack(fill="x", pady=2)
        port_cb = ctk.CTkCheckBox(port_frame, text="", variable=portable_var, width=24)
        port_cb.pack(side="left")
        port_label = ctk.CTkLabel(port_frame, text="Run in Portable Mode\n(all data in launcher folder)", justify="left", text_color="#dddddd")
        port_label.pack(side="left", padx=5)
        port_label.bind("<Button-1>", lambda e: port_cb.toggle())
        
        ctk.CTkLabel(scroll, text="⚠️ Enabling requires restart", text_color="#f1c40f",
                    font=ctk.CTkFont(size=10)).pack()

        # --- Java Info ---
        ctk.CTkLabel(scroll, text="Detected Java Installations:", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 5))
        if self.java_installations:
            for j in self.java_installations[:5]:
                ctk.CTkLabel(scroll, text=f"  Java {j['version']} ({j['vendor']}) - {j['path'][:60]}",
                            text_color="#aaaaaa", font=ctk.CTkFont(size=10)).pack(anchor="w")
            if len(self.java_installations) > 5:
                ctk.CTkLabel(scroll, text=f"  ... and {len(self.java_installations)-5} more",
                            text_color="#777777", font=ctk.CTkFont(size=10)).pack(anchor="w")
        else:
            ctk.CTkLabel(scroll, text="  No Java installations found", text_color="#e74c3c").pack(anchor="w")

        def rescan_java():
            self._update_ui_status("Scanning for Java...", "#f39c12")
            def scan():
                self.java_installations = scan_java_installations()
                self.after(0, lambda: self._update_ui_status(f"Found {len(self.java_installations)} Java installation(s)", "#27ae60"))
            threading.Thread(target=scan, daemon=True).start()

        ctk.CTkButton(scroll, text="Rescan Java", width=120, fg_color="#3498db",
                     command=rescan_java).pack(pady=5)

        # --- Backup Management ---
        ctk.CTkLabel(scroll, text="Backup Management:", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 5))
        all_backups = self.backup_manager.get_all_backups()
        ctk.CTkLabel(scroll, text=f"Total backups: {len(all_backups)} ({sum(self.backup_manager._get_dir_size(self.backup_manager.backup_dir / b['id']) for b in all_backups if (self.backup_manager.backup_dir / b['id']).exists()):,} bytes)",
                    text_color="#aaaaaa", font=ctk.CTkFont(size=11)).pack()

        def cleanup_backups():
            self.backup_manager.cleanup_old_backups()
            self._update_ui_status("Cleaned up old backups", "#27ae60")
        ctk.CTkButton(scroll, text="Cleanup Old Backups", width=160, fg_color="#e67e22",
                     command=cleanup_backups).pack(pady=5)

        # Save button
        def save_settings():
            new_theme = theme_var.get()
            old_theme = self.config.get("theme", DEFAULT_THEME)

            self.config["memory"] = int(mem_var.get())
            self.config["use_global_minecraft"] = use_global_var.get()
            self.config["theme"] = new_theme
            self.config["show_console"] = show_console_var.get()
            self.config["auto_backup"] = auto_backup_var.get()
            self.config["ssl_verify"] = ssl_verify_var.get()

            changed_mode = use_global_var.get() != self.config.get("use_global_minecraft")
            changed_theme = new_theme != old_theme
            changed_portable = portable_var.get() != self.using_portable

            self._save_config()

            settings_window.destroy()

            if changed_theme and new_theme in THEMES:
                apply_theme(new_theme)
                self._update_ui_status(f"Theme changed to {new_theme}", "#27ae60")

            if changed_mode:
                self._update_ui_status("Restart required for mode change", "#f1c40f")

            if changed_portable:
                if portable_var.get():
                    portable_mode.enable_portable_mode(self.launcher_dir)
                else:
                    portable_mode.disable_portable_mode(self.launcher_dir)
                self._update_ui_status("Restart required for portable mode change", "#f1c40f")

        ctk.CTkButton(scroll, text="Save Settings", fg_color="#27ae60", hover_color="#2ecc71",
                     command=save_settings, width=200, height=40).pack(pady=20)

    def setup_main_feed(self):
        # Main Content Frame (Update Feed)
        self.main_frame = ctk.CTkScrollableFrame(self.page_container, corner_radius=0, fg_color="transparent")
        self.main_frame.grid_columnconfigure(0, weight=1)

        header_label = ctk.CTkLabel(self.main_frame, text="Minecraft Official News", font=ctk.CTkFont(size=20, weight="bold"))
        header_label.grid(row=0, column=0, sticky="w", pady=(0, 20))

        # Dynamically fetch real Minecraft news in a background thread
        threading.Thread(target=self.fetch_real_minecraft_news, daemon=True).start()

    def fetch_real_minecraft_news(self):
        import urllib.request
        import json
        
        updates = []
        try:
            # Fetch official JSON news feed used by the real launcher
            url = "https://launchercontent.mojang.com/news.json"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                
            # Parse top 5 entries
            for entry in data.get("entries", [])[:5]:
                title = entry.get("title", "Minecraft Update")
                text = entry.get("text", "Read more on Minecraft.net")
                updates.append((title, text))
                
        except Exception as e:
            updates = [
                ("Could not connect to Minecraft servers", "Make sure you are connected to the internet to see the latest game updates.")
            ]
            
        # Update the UI from the main thread
        self.after(0, self.render_news_cards, updates)

    def render_news_cards(self, updates):
        for i, (title, text) in enumerate(updates):
            card = ctk.CTkFrame(self.main_frame, corner_radius=10, fg_color="#2b2b2b")
            card.grid(row=i+1, column=0, sticky="ew", pady=10)
            card.grid_columnconfigure(0, weight=1)
            
            # FIX: Increased text brightness for better contrast on dark background
            ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=16, weight="bold"), text_color="#60d0ff").grid(row=0, column=0, sticky="w", padx=15, pady=(15, 5))
            
            # Clean html tags from text minimally and truncate if too long
            clean_text = text.replace("<p>", "").replace("</p>", "").replace("<b>", "").replace("</b>", "")
            if len(clean_text) > 300:
                clean_text = clean_text[:297] + "..."
                
            ctk.CTkLabel(card, text=clean_text, wraplength=600, justify="left", text_color="#e0e0e0").grid(row=1, column=0, sticky="w", padx=15, pady=(0, 15))

    def setup_bottom_bar(self):
        # Bottom Control Bar - properly sized to contain all elements
        self.bottom_bar = ctk.CTkFrame(self, corner_radius=0, fg_color="#1e1e1e")
        self.bottom_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.bottom_bar.grid_columnconfigure(4, weight=1) # Spacer

        # Username with clear placeholder
        self.username_entry = ctk.CTkEntry(self.bottom_bar, placeholder_text="Enter Offline Username...", width=200)
        self.username_entry.insert(0, "DRAGO")
        self.username_entry.grid(row=0, column=0, padx=(20, 10), pady=10)

        # Login with Microsoft Button
        self.btn_microsoft_login = ctk.CTkButton(self.bottom_bar, text="Login with MS", width=120, fg_color="#107c10", hover_color="#1f8b22", command=self.start_microsoft_login)
        self.btn_microsoft_login.grid(row=1, column=0, padx=(20, 10), pady=(0, 10))

        # Dynamically fetch versions (Both installed and available online)
        mine_dir = self._get_global_minecraft_dir()
        
        if os.path.exists(mine_dir):
            try:
                raw_installed = minecraft_launcher_lib.utils.get_installed_versions(mine_dir)
                installed_versions = [v['id'] for v in raw_installed]
            except Exception:
                pass
                
        # Fetch all online releases
        all_versions = []
        try:
            import re
            version_list = minecraft_launcher_lib.utils.get_version_list()
            for v in version_list:
                if v['type'] == 'release':
                    version_id = v['id']
                    # Accept both old format (1.X.X) and new format (YY.D.H)
                    # Old: 1.20.1, 1.19.4, 1.16.5, etc.
                    # New: 26.1, 26.1.1, 26.1.2, etc. (2026 onwards)
                    if re.match(r'^(1\.\d+(\.\d+)?|2[6-9]\.\d+(\.\d+)?)$', version_id):
                        all_versions.append(version_id)
            print(f"DEBUG: Fetched {len(all_versions)} valid Minecraft versions")
        except Exception as e:
            print(f"DEBUG: Failed to fetch online versions: {e}")
            all_versions = ["26.1.2", "26.1.1", "26.1", "1.21.4", "1.21.3", "1.21.1", "1.20.6", "1.20.4", "1.20.1", "1.19.4", "1.19.2", "1.18.2", "1.17.1", "1.16.5", "1.12.2"] # Fallback

        print(f"DEBUG: Installed versions: {len(installed_versions)}")
        print(f"DEBUG: Valid online versions: {len(all_versions)}")
        
        self.installed_versions_cache = installed_versions
        self.version_id_to_display = {}  # Map display name to actual ID
        dropdown_values = []
        
        # Helper function to get friendly name for a version
        def get_friendly_name(version_id):
            # Check if it's a modded version by reading JSON
            version_json_path = os.path.join(mine_dir, "versions", version_id, f"{version_id}.json")
            if os.path.exists(version_json_path):
                try:
                    with open(version_json_path, 'r') as f:
                        version_data = json.load(f)
                        if 'inheritsFrom' in version_data:
                            mc_version = version_data['inheritsFrom']
                            # Detect loader type
                            if 'fabric' in version_id.lower():
                                return f"Fabric {mc_version}"
                            elif 'forge' in version_id.lower():
                                return f"Forge {mc_version}"
                            elif 'quilt' in version_id.lower():
                                return f"Quilt {mc_version}"
                            else:
                                return f"Modded {mc_version}"
                except Exception:
                    pass
            return version_id  # Return as-is if can't determine
        
        # Add installed versions first with friendly names
        for iv in installed_versions:
            friendly_name = get_friendly_name(iv)
            self.version_id_to_display[friendly_name] = iv
            if friendly_name not in dropdown_values:
                dropdown_values.append(friendly_name)
            
        # Add online versions that aren't installed yet
        for v in all_versions:
            if v not in installed_versions and v not in dropdown_values:
                dropdown_values.append(v)
                self.version_id_to_display[v] = v
        
        self.dropdown_values = dropdown_values
        self.fetch_optifine_versions()
        dropdown_values = self.dropdown_values
        
        print(f"DEBUG: Total dropdown values: {len(dropdown_values)}")
        print(f"DEBUG: First 10 values: {dropdown_values[:10]}")
                
        if not dropdown_values:
            dropdown_values = ["No versions found"]

        # Memory / Remember last selection
        saved_version_id = self.config.get("last_version", dropdown_values[0])
        # Find the display name for saved version
        saved_display = saved_version_id
        for display, vid in self.version_id_to_display.items():
            if vid == saved_version_id:
                saved_display = display
                break
        
        if saved_display not in dropdown_values:
            saved_display = dropdown_values[0]

        # Custom Version Dropdown (Scrollable)
        self.version_var = ctk.StringVar(value=saved_display)
        self.dropdown_values = dropdown_values
        
        # Frame to hold Version button + Verify/Delete
        self.version_frame = ctk.CTkFrame(self.bottom_bar, fg_color="transparent")
        self.version_frame.grid(row=0, column=1, padx=10, pady=10)
        
        self.version_button = ctk.CTkButton(self.version_frame, textvariable=self.version_var, 
                                            width=200, fg_color="#2b2b2b", hover_color="#3a3a3a", 
                                            anchor="w", command=self.open_version_dropdown)
        self.version_button.pack(fill="x")
        
        self.version_actions_frame = ctk.CTkFrame(self.version_frame, fg_color="transparent")
        self.version_actions_frame.pack(fill="x", pady=(5, 0))

        self.btn_verify = ctk.CTkButton(self.version_actions_frame, text="Verify/Repair", width=95, height=20, font=ctk.CTkFont(size=11), fg_color="#2980b9", hover_color="#3498db", command=self.verify_version)
        self.btn_verify.pack(side="left", padx=(0, 5))

        self.btn_delete = ctk.CTkButton(self.version_actions_frame, text="Delete", width=95, height=20, font=ctk.CTkFont(size=11), fg_color="#c0392b", hover_color="#e74c3c", command=self.delete_version)
        self.btn_delete.pack(side="right")

        # Dropdown window holder
        self.dropdown_window = None

        # Status & Progress Container
        self.status_container = ctk.CTkFrame(self.bottom_bar, fg_color="transparent")
        self.status_container.grid(row=0, column=2, padx=10, sticky="w")
        
        # Status Label
        self.status_label = ctk.CTkLabel(self.status_container, text="Ready", text_color="#aaaaaa", width=250, anchor="w")
        self.status_label.pack(anchor="w")
        
        # Progress Bar (Hidden initially)
        self.progress_bar = ctk.CTkProgressBar(self.status_container, width=250)
        self.progress_bar.set(0)
        self.progress_bar.pack(anchor="w", pady=(5,0))
        self.progress_bar.pack_forget() # Hide it

        # Big Play Button (Green) - single row, properly contained
        self.play_button = ctk.CTkButton(self.bottom_bar, text="▶ PLAY", 
                                        font=ctk.CTkFont(size=14, weight="bold"),
                                        fg_color="#27ae60", hover_color="#2ecc71", 
                                        height=35, width=140,
                                        command=self.start_launch_thread)
        self.play_button.grid(row=0, column=5, padx=15, pady=10)
        
        # Update play button text with instance name
        self.update_play_button_text()
    
    def update_play_button_text(self):
        """Update play button text - simplified to just PLAY"""
        # FIX: Simple "▶ PLAY" text as requested - high-visibility green for main action
        self.play_button.configure(text="▶ PLAY")

    def set_gpu_preference(self, java_path):
        if platform.system() != "Windows":
            return
        try:
            import winreg
            key_path = r"Software\Microsoft\DirectX\UserGpuPreferences"
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
            except FileNotFoundError:
                key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
            
            winreg.SetValueEx(key, java_path, 0, winreg.REG_SZ, "GpuPreference=2;")
            winreg.CloseKey(key)
        except Exception as e:
            print(f"Failed to set GPU preference: {e}")

    def get_rtx3050_jvm_args(self):
        ram = int(self.config.get("memory", 6))

        args = [
            f"-Xmx{ram}G",
            f"-Xms{ram}G",
            "-XX:+UnlockExperimentalVMOptions",
            "-XX:+UseG1GC",
            "-XX:G1NewSizePercent=20",
            "-XX:G1ReservePercent=20",
            "-XX:MaxGCPauseMillis=50",
            "-XX:G1HeapRegionSize=32M",
            "-Dcustomskinloader.enabled=true"
        ]

        # 1.16.5 offline multiplayer workaround
        if self.version_var.get() == "1.16.5":
            args.extend([
                "-Dminecraft.api.auth.host=https://nope.invalid",
                "-Dminecraft.api.account.host=https://nope.invalid",
                "-Dminecraft.api.session.host=https://nope.invalid",
                "-Dminecraft.api.services.host=https://nope.invalid"
            ])

        return args

    def _update_ui_status(self, text, color):
        self.status_label.configure(text=text, text_color=color)

    def start_microsoft_login(self):
        self._update_ui_status("Starting Microsoft Login...", "#f39c12")
        threading.Thread(target=self._microsoft_login_thread, daemon=True).start()

    def _microsoft_login_thread(self):
        try:
            # Hardcoded public Client ID for Drago Launcher (Completely safe for public clients)
            client_id = "ab5dd215-1a94-4383-a5f2-d51d42ab758f"
            
            auth_manager = XSTSIdentityManager(client_id=client_id)
            
            async def run_device_flow():
                device_info = await auth_manager.start_device_authorization()
                user_code = device_info["user_code"]
                verification_uri = device_info["verification_uri"]
                interval = device_info.get("interval", 5)
                device_code = device_info["device_code"]
                
                # Copy to clipboard and open browser
                try:
                    self.clipboard_clear()
                    self.clipboard_append(user_code)
                except Exception:
                    pass
                
                msg = f"Go to {verification_uri} and enter: {user_code} (Copied!)"
                self.after(0, lambda: self._update_ui_status(msg, "#3498db"))
                
                import webbrowser
                webbrowser.open(verification_uri)
                
                # Poll for completion
                oauth = await auth_manager.poll_device_authorization(device_code, interval)
                self.after(0, lambda: self._update_ui_status("Authenticating with Minecraft...", "#f39c12"))
                return await auth_manager.get_minecraft_profile(oauth)

            mc_token, profile = asyncio.run(run_device_flow())
            
            self.authenticated_xuid = profile["id"]
            self.authenticated_token = mc_token
            name = profile["name"]
            
            # Update UI on success
            self.after(0, lambda n=name: self._update_ui_status(f"Logged in as {n}", "#27ae60"))
            self.after(0, lambda: self.username_entry.delete(0, 'end'))
            self.after(0, lambda n=name: self.username_entry.insert(0, n))
            
        except Exception as e:
            err = str(e)
            self.after(0, lambda msg=err: self._update_ui_status(f"Login error: {msg}", "#c0392b"))

    def _install_progress_callback(self, current, max_val):
        # Calculate percentage
        if max_val > 0:
            percentage = current / max_val
            self.progress_bar.set(percentage)
            
    def start_launch_thread(self):
        threading.Thread(target=self.launch_thread, daemon=True).start()

    def open_version_dropdown(self):
        if self.dropdown_window is not None and self.dropdown_window.winfo_exists():
            self.dropdown_window.destroy()
            return
            
        self.dropdown_window = ctk.CTkToplevel(self)
        self.dropdown_window.overrideredirect(True)
        # FIX: Set high z-index to prevent overlapping with other UI elements
        self.dropdown_window.attributes("-topmost", True)
        self.dropdown_window.wm_attributes("-toolwindow", True)
        
        # Get absolute position of the button - anchor properly relative to parent
        x = self.version_button.winfo_rootx()
        btn_y = self.version_button.winfo_rooty()
        btn_height = self.version_button.winfo_height()
        
        # Determine optimal height (max 300, or adapt to screen)
        dropdown_height = min(300, len(self.dropdown_values) * 32 + 10)
        # FIX: Position above button using bottom: 100%; left: 0; equivalent
        y = btn_y - dropdown_height - 5  # Small gap for visual separation
        
        self.dropdown_window.geometry(f"{self.version_button.winfo_width()}x{dropdown_height}+{x}+{y}")
        
        # FIX: Enhanced border with box-shadow equivalent for depth and visual separation
        main_border = ctk.CTkFrame(self.dropdown_window, fg_color="#2b2b2b", border_width=2, border_color="#3498db", corner_radius=8)
        main_border.pack(fill="both", expand=True, padx=3, pady=3)

        # Scrollable frame for versions
        scroll_frame = ctk.CTkScrollableFrame(main_border, fg_color="transparent", corner_radius=0)
        scroll_frame.pack(fill="both", expand=True, padx=2, pady=2)
        
        def select_version(v):
            self.version_var.set(v)
            self.dropdown_window.destroy()
            
            # Save actual version ID to config (not display name)
            actual_id = self.version_id_to_display.get(v, v)
            self.config["last_version"] = actual_id
            try:
                with open(self.config_file, "w") as f:
                    json.dump(self.config, f)
            except:
                pass
            
        for v in self.dropdown_values:
            # Get actual version ID for checking if installed
            actual_id = self.version_id_to_display.get(v, v)
            # Highlight installed versions! Bright white bold for installed, dimmer gray for uninstalled
            if actual_id in self.installed_versions_cache:
                txt_color = "#ffffff"
                font_weight = "bold"
            else:
                txt_color = "#777777"
                font_weight = "normal"
                
            btn = ctk.CTkButton(scroll_frame, text=v, fg_color="transparent", hover_color="#3a7ebf", 
                                text_color=txt_color, font=ctk.CTkFont(weight=font_weight),
                                anchor="w", height=30,
                                command=lambda ver=v: select_version(ver))
            btn.pack(fill="x", pady=1, padx=2)
            
        # Click outside to close
        self.dropdown_window.bind("<FocusOut>", lambda e: self.dropdown_window.destroy())
        self.dropdown_window.focus_set()

    def launch_thread(self):
        display_version = self.version_var.get()
        # Get actual version ID from display name
        version = self.version_id_to_display.get(display_version, display_version)
        name = self.username_entry.get().strip() or "DRAGO"
        
        # Check if using global .minecraft or instance system
        use_global = self.config.get("use_global_minecraft", False)
        
        if use_global:
            mine_dir = self._get_global_minecraft_dir()
        else:
            current_instance_id = self.config.get("current_instance")
            if not current_instance_id:
                self._update_ui_status("No instance selected!", "#e74c3c")
                return
            
            instance = self.instance_manager.get_instance(current_instance_id)
            if not instance:
                self._update_ui_status("Instance not found!", "#e74c3c")
                return
            
            # Use instance-specific directory
            instance_path = self.instance_manager.get_instance_path(current_instance_id)
            mine_dir = str(instance_path)
            
            # Use instance version if not manually overridden
            if version == "No versions found" or not version:
                version = instance['version']

        # Stable UUID (important for legacy versions)
        current_uuid = self.config.get("uuid", "").strip()
        if not current_uuid:
            import uuid
            current_uuid = str(uuid.uuid4()).replace("-", "")
            self.config["uuid"] = current_uuid
            with open(self.config_file, "w") as f:
                json.dump(self.config, f)

        # --- Safe Mode: temporarily disable mods/shaders/resourcepacks ---
        safe_mode = False
        if not use_global and instance:
            safe_mode = instance.get('settings', {}).get('safe_mode', False) or self.config.get("safe_mode", False)

        if safe_mode and not use_global:
            self._update_ui_status("🔒 Safe Mode: disabling mods/shaders/resourcepacks...", "#f39c12")
            import shutil
            import tempfile
            instance_path = Path(mine_dir)
            safe_mode_backups = {}
            for folder in ["mods", "shaderpacks"]:
                src = instance_path / folder
                if src.exists():
                    backup_path = Path(tempfile.gettempdir()) / f"drago_safe_{folder}"
                    if backup_path.exists():
                        shutil.rmtree(backup_path)
                    shutil.copytree(src, backup_path)
                    safe_mode_backups[folder] = backup_path
                    for item in src.iterdir():
                        if item.is_file() or item.is_dir():
                            if item.is_dir():
                                shutil.rmtree(item)
                            else:
                                item.unlink()
            rp_dir = instance_path / "resourcepacks"
            if rp_dir.exists():
                rp_backup = Path(tempfile.gettempdir()) / "drago_safe_resourcepacks"
                if rp_backup.exists():
                    shutil.rmtree(rp_backup)
                shutil.copytree(rp_dir, rp_backup)
                safe_mode_backups["resourcepacks"] = rp_backup

        # --- Auto-backup before launch ---
        if not use_global and self.config.get("auto_backup", True):
            self._update_ui_status("Creating pre-launch backup...", "#f39c12")
            self.backup_manager.auto_backup_before_launch(current_instance_id)

        try:
            # Check for Optifine installation
            if "OptiFine" in version:
                self.check_and_download_optifine(version, mine_dir)

            # Install absolute vanilla version if missing
            version_path = os.path.join(mine_dir, "versions", version)
            if not os.path.exists(version_path) and "OptiFine" not in version:
                self._update_ui_status(f"Downloading {version}...", "#3498db")
                self.progress_bar.pack(pady=10)

                callback = {
                    "setStatus": lambda text: self._update_ui_status(text, "#3498db"),
                    "setProgress": lambda progress: self.progress_bar.set(float(progress) / 100),
                    "setMax": lambda max_progress: None
                }

                minecraft_launcher_lib.install.install_minecraft_version(
                    version,
                    mine_dir,
                    callback=callback
                )

            # Detect legacy versions
            is_legacy = False
            try:
                version_num = float(".".join(version.split(".")[:2]))
                is_legacy = version_num < 1.18
            except Exception:
                pass

            # Get RAM settings (from instance or global config)
            if use_global:
                ram_max = self.config.get('memory', 6)
                ram_min = 2
            else:
                settings = instance['settings']
                ram_max = settings.get('ram_max', 4)
                # Match Xms to Xmx per requirement
                ram_min = ram_max

            # Build JVM arguments
            jvm_args = [
                f"-Xmx{ram_max}G",
                f"-Xms{ram_min}G",
                "-XX:+UnlockExperimentalVMOptions",
                "-XX:+UseG1GC",
                "-XX:G1NewSizePercent=20",
                "-XX:G1ReservePercent=20",
                "-XX:MaxGCPauseMillis=50",
                "-XX:G1HeapRegionSize=32M",
                "-Dcustomskinloader.enabled=true"
            ]

            # Add custom JVM args from instance if not using global
            if not use_global and instance.get('settings', {}).get('jvm_args'):
                jvm_args.extend(instance['settings']['jvm_args'])

            # 1.16.5 offline multiplayer workaround
            if version == "1.16.5":
                jvm_args.extend([
                    "-Dminecraft.api.auth.host=https://nope.invalid",
                    "-Dminecraft.api.account.host=https://nope.invalid",
                    "-Dminecraft.api.session.host=https://nope.invalid",
                    "-Dminecraft.api.services.host=https://nope.invalid"
                ])

            # Launch options
            options = {
                "username": name,
                "uuid": getattr(self, "authenticated_xuid", current_uuid),
                "token": getattr(self, "authenticated_token", "FML"),
                "jvmArguments": jvm_args,
                "launcher_name": "minecraft-launcher",
                "launcher_version": "3.32.9",
                "userType": "mojang" if is_legacy else "msa",
                "versionType": "release",
                "demo": False,
                "meta": {
                    "demo": False,
                    "custom": True
                }
            }

            # Add resolution settings if using instance system
            if not use_global and instance:
                settings = instance['settings']
                if settings.get('resolution_width') and settings.get('resolution_height'):
                    options['customResolution'] = True
                    options['resolutionWidth'] = str(settings['resolution_width'])
                    options['resolutionHeight'] = str(settings['resolution_height'])

                if settings.get('fullscreen'):
                    options['fullscreen'] = True

            # Build launch command
            command = minecraft_launcher_lib.command.get_minecraft_command(
                version,
                mine_dir,
                options
            )

            # Remove all demo flags
            while "--demo" in command:
                command.remove("--demo")

            # Clean legacy auth arguments for 1.16.5
            if version == "1.16.5":
                for arg in [
                    "--accessToken",
                    "--uuid",
                    "--userType",
                    "--userProperties",
                    "--profileProperties",
                    "--xuid",
                    "--clientId",
                    "--session"
                ]:
                    while arg in command:
                        idx = command.index(arg)
                        del command[idx:idx + 2]

                command.extend([
                    "--accessToken", "FML",
                    "--uuid", current_uuid,
                    "--userType", "mojang",
                    "--userProperties", "{}",
                    "--profileProperties", "{}"
                ])

            # Force full release mode
            if "--versionType" in command:
                idx = command.index("--versionType")
                if idx + 1 < len(command):
                    command[idx + 1] = "release"

            # Smart Java path selection
            if use_global:
                java_path = minecraft_launcher_lib.utils.get_java_executable()
            else:
                java_path = instance['settings'].get('java_path')
                if not java_path:
                    suggested = suggest_java_for_instance(self.java_installations, instance.get('version', version))
                    java_path = suggested or minecraft_launcher_lib.utils.get_java_executable()

            if java_path:
                command[0] = java_path
                # Automate GPU Preference to High Performance (2)
                self.set_gpu_preference(java_path)

            # Debug final command
            print("FINAL COMMAND:")
            print(" ".join(command))

            # Launch
            launch_name = "Global .minecraft" if use_global else instance['name']
            self._update_ui_status(f"Launching {launch_name}...", "#27ae60")
            self.progress_bar.pack_forget()
            self.play_button.configure(state="normal")

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )

            # Show console viewer if enabled
            console_viewer = None
            if self.config.get("show_console", True):
                console_viewer = spawn_console(self, process, title=f"Minecraft - {launch_name}")

            # Process Priority (High = 0x00000080)
            if platform.system() == "Windows":
                try:
                    import ctypes
                    PROCESS_ALL_ACCESS = 0x1F0FFF
                    handle = ctypes.windll.kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, process.pid)
                    if handle:
                        ctypes.windll.kernel32.SetPriorityClass(handle, 0x00000080)
                        ctypes.windll.kernel32.CloseHandle(handle)
                        print(f"Successfully applied Priority High to PID {process.pid}")
                except Exception as priority_err:
                    print(f"Failed to set CPU properties: {priority_err}")

            # Update play stats if using instance system
            if not use_global:
                self.instance_manager.update_play_stats(current_instance_id, 0)

            self._update_ui_status("Game Running!", "#27ae60")

            process.wait()

            # Restore safe mode files
            if safe_mode and not use_global:
                try:
                    import shutil
                    for folder, backup_path in safe_mode_backups.items():
                        target = instance_path / folder
                        if backup_path.exists():
                            if target.exists():
                                shutil.rmtree(target)
                            shutil.copytree(backup_path, target)
                            shutil.rmtree(backup_path)
                except Exception as e:
                    print(f"Safe mode restore error: {e}")

            self._update_ui_status("Ready to play", "#aaaaaa")

        except Exception as e:
            self._update_ui_status("Launch Error!", "#e74c3c")
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            self.play_button.configure(state="normal")

            # Restore safe mode files on error
            if safe_mode and not use_global:
                try:
                    for folder, backup_path in safe_mode_backups.items():
                        target = instance_path / folder
                        if backup_path.exists():
                            if target.exists():
                                shutil.rmtree(target)
                            shutil.copytree(backup_path, target)
                            shutil.rmtree(backup_path)
                except Exception:
                    pass
    def verify_version(self):
        version = self.version_var.get()
        if not version or version == "No versions found":
            return
        
        self._update_ui_status(f"Verifying/Repairing {version}...", "#f1c40f")
        threading.Thread(target=self._run_verify, args=(version,), daemon=True).start()

    def _run_verify(self, version):
        self.play_button.configure(state="disabled")
        self.progress_bar.pack(anchor="w", pady=(5,0)) 
        self.progress_bar.set(0)
        
        current_max = 0
        def set_max(val): nonlocal current_max; current_max = val
        def set_progress(val): self._install_progress_callback(val, current_max)
        def set_status(val): self._update_ui_status(f"Checking: {val}", "#3498db")

        callback = { "setStatus": set_status, "setProgress": set_progress, "setMax": set_max }
        
        try:
            mine_dir = self._get_global_minecraft_dir()
            minecraft_launcher_lib.install.install_minecraft_version(version, mine_dir, callback=callback)
            self._update_ui_status("Version Verified & Repaired!", "#27ae60")
            
            if version not in self.installed_versions_cache:
                self.installed_versions_cache.append(version)
        except Exception as e:
            self._update_ui_status("Verification Failed!", "#e74c3c")
            
        self.progress_bar.pack_forget()
        self.play_button.configure(state="normal")

    def delete_version(self):
        version = self.version_var.get()
        if not version or version == "No versions found":
            return
            
        mine_dir = self._get_global_minecraft_dir()
        version_dir = os.path.join(mine_dir, "versions", version)

        if os.path.exists(version_dir):
            try:
                import shutil
                shutil.rmtree(version_dir)
                self._update_ui_status(f"Deleted {version}!", "#27ae60")
                if version in self.installed_versions_cache:
                    self.installed_versions_cache.remove(version)
            except Exception as e:
                self._update_ui_status(f"Error Deleting {version}", "#e74c3c")
        else:
            self._update_ui_status(f"{version} is not installed.", "#aaaaaa")
            
if __name__ == "__main__":
    app = DragoLauncher()
    app.mainloop()