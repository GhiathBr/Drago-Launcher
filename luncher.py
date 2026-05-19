import customtkinter as ctk
import minecraft_launcher_lib
import subprocess
import os
import sys
import threading
import json
import requests
import warnings
from urllib3.exceptions import InsecureRequestWarning
from instance_manager import InstanceManager

# Suppress insecure request warnings and globally disable SSL verification
# This bypasses strict antivirus/firewall deep packet inspection (e.g. Avast) that breaks downloads
warnings.simplefilter('ignore', InsecureRequestWarning)
original_request = requests.Session.request

def patched_request(self, method, url, **kwargs):
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
        
        self.CURRENT_VERSION = "v1.2"
        
        # Load Config from AppData/.minecraft globally (hiding it)
        mine_dir = os.path.expandvars(r'%APPDATA%\.minecraft')
        if not os.path.exists(mine_dir):
            os.makedirs(mine_dir, exist_ok=True)
            
        self.config_file = os.path.join(mine_dir, "drago_launcher_config.json")
        
        # Keep backward compatibility by moving an old config if it exists alongside the app
        old_config_file = "drago_launcher_config.json"
        if os.path.exists(old_config_file) and not os.path.exists(self.config_file):
            import shutil
            shutil.move(old_config_file, self.config_file)
            
        self.config = {"last_version": "", "memory": 6, "current_instance": None, "use_global_minecraft": True}
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    self.config.update(json.load(f))
            except Exception:
                pass
        
        # Set default to global .minecraft if not explicitly configured
        if "use_global_minecraft" not in self.config:
            self.config["use_global_minecraft"] = True
            self._save_config()
        
        # Initialize Instance Manager
        self.instance_manager = InstanceManager()
        
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

        # Nav Buttons (Blue)
        self.btn_home = ctk.CTkButton(self.sidebar_frame, text="Home", fg_color="#1f538d", anchor="w", command=self.show_news_page)
        self.btn_home.grid(row=2, column=0, padx=20, pady=10)
        
        self.btn_instances = ctk.CTkButton(self.sidebar_frame, text="Instances", fg_color="#1f538d", anchor="w", command=self.show_instances_page)
        self.btn_instances.grid(row=3, column=0, padx=20, pady=10)

        self.btn_mods = ctk.CTkButton(self.sidebar_frame, text="Game Content Browser", fg_color="#1f538d", anchor="w", command=self.show_content_page)
        self.btn_mods.grid(row=4, column=0, padx=20, pady=10)

        self.btn_update = ctk.CTkButton(self.sidebar_frame, text="Check for Updates", fg_color="#2ecc71", anchor="w", command=self.check_for_updates)
        self.btn_update.grid(row=5, column=0, padx=20, pady=10)

        self.btn_settings = ctk.CTkButton(self.sidebar_frame, text="Settings", fg_color="#1f538d", anchor="w", command=self.open_settings)
        self.btn_settings.grid(row=6, column=0, padx=20, pady=20)

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
        dialog.geometry("450x450")  # Increased from 400 to 450
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)  # Prevent resizing
        
        ctk.CTkLabel(dialog, text="Create New Instance", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=20)
        
        # Name
        ctk.CTkLabel(dialog, text="Instance Name:").pack(pady=(10, 0))
        name_entry = ctk.CTkEntry(dialog, width=300, placeholder_text="My Awesome Instance")
        name_entry.pack(pady=5)
        
        # Version
        ctk.CTkLabel(dialog, text="Minecraft Version:").pack(pady=(10, 0))
        version_var = ctk.StringVar(value="1.20.1")
        
        # Get available versions
        available_versions = ["1.20.1", "1.19.4", "1.18.2", "1.16.5", "1.12.2"]
        try:
            online_versions = [v['id'] for v in minecraft_launcher_lib.utils.get_version_list() 
                             if v['type'] == 'release'][:20]
            available_versions = online_versions
        except:
            pass
        
        version_menu = ctk.CTkOptionMenu(dialog, variable=version_var, values=available_versions, width=300)
        version_menu.pack(pady=5)
        
        # Loader
        ctk.CTkLabel(dialog, text="Mod Loader:").pack(pady=(10, 0))
        loader_var = ctk.StringVar(value="vanilla")
        loader_menu = ctk.CTkOptionMenu(dialog, variable=loader_var, 
                                       values=["vanilla", "fabric", "forge", "quilt", "neoforge"], 
                                       width=300)
        loader_menu.pack(pady=5)
        
        # Buttons
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=30)
        
        def create():
            name = name_entry.get().strip()
            if not name:
                name = f"Instance {len(self.instance_manager.get_all_instances()) + 1}"
            
            instance_id = self.instance_manager.create_instance(
                name=name,
                version=version_var.get(),
                loader=loader_var.get()
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
        dialog.geometry("520x720")  # Increased width and height for better spacing
        dialog.transient(self)
        dialog.resizable(False, False)  # Prevent resizing
        
        # Main container with fixed button at bottom
        main_container = ctk.CTkFrame(dialog, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=20, pady=20)
        main_container.grid_rowconfigure(0, weight=1)
        main_container.grid_columnconfigure(0, weight=1)
        
        # Scrollable content
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
        ctk.CTkCheckBox(scroll, text="⭐ Mark as Favorite", variable=favorite_var).pack(pady=10)
        
        # RAM Settings
        ctk.CTkLabel(scroll, text="RAM Allocation:", anchor="w", font=ctk.CTkFont(weight="bold")).pack(fill="x", pady=(20, 5))
        
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
        ctk.CTkLabel(scroll, text="Window Resolution:", anchor="w", font=ctk.CTkFont(weight="bold")).pack(fill="x", pady=(20, 5))
        
        res_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        res_frame.pack(fill="x", pady=5)
        
        width_var = ctk.StringVar(value=str(settings.get('resolution_width', 854)))
        height_var = ctk.StringVar(value=str(settings.get('resolution_height', 480)))
        
        ctk.CTkEntry(res_frame, textvariable=width_var, width=100, placeholder_text="Width").pack(side="left", padx=5)
        ctk.CTkLabel(res_frame, text="×").pack(side="left")
        ctk.CTkEntry(res_frame, textvariable=height_var, width=100, placeholder_text="Height").pack(side="left", padx=5)
        
        fullscreen_var = ctk.BooleanVar(value=settings.get('fullscreen', False))
        ctk.CTkCheckBox(scroll, text="Start in Fullscreen", variable=fullscreen_var).pack(pady=5)
        
        # Java Path
        ctk.CTkLabel(scroll, text="Java Path (leave empty for auto):", anchor="w", font=ctk.CTkFont(weight="bold")).pack(fill="x", pady=(20, 5))
        java_entry = ctk.CTkEntry(scroll, width=400, placeholder_text="Auto-detect")
        if settings.get('java_path'):
            java_entry.insert(0, settings['java_path'])
        java_entry.pack(pady=5)
        
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
                'game_args': settings.get('game_args', [])
            }
            
            self.instance_manager.update_instance_settings(instance_id, new_settings)
            self.instance_manager.rename_instance(instance_id, name_entry.get().strip())
            self.instance_manager.set_favorite(instance_id, favorite_var.get())
            
            self.refresh_instances_list()
            dialog.destroy()
            self._update_ui_status("Settings saved", "#27ae60")
        
        # Button container at bottom (outside scroll)
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
        
        # Tabs for Content
        tabview = ctk.CTkTabview(self.content_browser_frame)
        tabview.grid(row=1, column=0, sticky="nsew")
        
        tabview.add("Skins Manager")
        tabview.add("Modrinth Mods & Worlds")
        tabview.add("Installed Content")
        
        # === SKINS TAB ===
        skin_tab = tabview.tab("Skins Manager")
        
        self.skin_preview_label = ctk.CTkLabel(skin_tab, text="No Skin Loaded", image=None)
        self.skin_preview_label.pack(pady=20)
        
        self.load_visual_skin() # Try to load on boot

        def browse_skin():
            from tkinter import filedialog
            import shutil
            
            filepath = filedialog.askopenfilename(title="Select Skin", filetypes=[("PNG Files", "*.png")])
            if filepath:
                username = self.username_entry.get().strip() or "DRAGO"
                mine_dir = os.path.expandvars(r'%APPDATA%\.minecraft')
                
                skin_dir = os.path.join(mine_dir, "CustomSkinLoader", "LocalSkin", "skins")
                os.makedirs(skin_dir, exist_ok=True)
                
                target_path = os.path.join(skin_dir, f"{username}.png")
                try:
                    shutil.copy(filepath, target_path)
                    
                    csl_config_dir = os.path.join(mine_dir, "CustomSkinLoader")
                    csl_config_path = os.path.join(csl_config_dir, "CustomSkinLoader.json")
                    
                    config_data = {
                        "version": "14.0",
                        "enable": True,
                        "loadlist": [
                            {"name": "LocalSkin", "type": "LocalSkin"},
                            {"name": "Mojang", "type": "MojangAPI"},
                            {"name": "Ely.by", "type": "ElyBy"},
                            {"name": "LittleSkin", "type": "CustomSkinAPI", "root": "https://littleskin.cn/api/yggdrasil"}
                        ]
                    }
                    with open(csl_config_path, "w") as config_file:
                        json.dump(config_data, config_file, indent=4)
                        
                    status_lbl.configure(text=f"Skin applied! Applied to all servers/clients.", text_color="#27ae60")
                    self.load_visual_skin()
                except Exception as e:
                    status_lbl.configure(text=f"Error copying skin: {e}", text_color="#e74c3c")

        browse_btn = ctk.CTkButton(skin_tab, text="Upload Skin (.png)", fg_color="#8e44ad", hover_color="#9b59b6", command=browse_skin)
        browse_btn.pack(pady=5)
        
        status_lbl = ctk.CTkLabel(skin_tab, text="")
        status_lbl.pack()
        
        # === MODRINTH BROWSER TAB ===
        mod_tab = tabview.tab("Modrinth Mods & Worlds")
        mod_tab.grid_columnconfigure(0, weight=1)
        mod_tab.grid_rowconfigure(2, weight=1)
        
        # Version indicator at top
        self.mod_version_label = ctk.CTkLabel(mod_tab, text="Browsing mods for: Minecraft 1.21.1", 
                                              font=ctk.CTkFont(size=12, weight="bold"), 
                                              text_color="#3498db")
        self.mod_version_label.grid(row=0, column=0, sticky="w", padx=5, pady=(5, 0))
        
        # Mod loader warning label
        self.mod_loader_warning = ctk.CTkLabel(mod_tab, text="", 
                                               font=ctk.CTkFont(size=11),
                                               text_color="#e74c3c")
        self.mod_loader_warning.grid(row=0, column=0, sticky="e", padx=5, pady=(5, 0))
        
        self.search_frame = ctk.CTkFrame(mod_tab, fg_color="transparent")
        self.search_frame.grid(row=1, column=0, sticky="ew", pady=5)
        self.search_frame.grid_columnconfigure(0, weight=1)
        
        self.mod_search_entry = ctk.CTkEntry(self.search_frame, placeholder_text="Search Mods or Modpacks...")
        self.mod_search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        
        search_btn = ctk.CTkButton(self.search_frame, text="Search", width=80, command=lambda: threading.Thread(target=self.search_modrinth).start())
        search_btn.grid(row=0, column=1)
        
        self.mod_results_frame = ctk.CTkScrollableFrame(mod_tab, fg_color="#1e1e1e")
        self.mod_results_frame.grid(row=2, column=0, sticky="nsew", pady=5)
        self.mod_results_frame.grid_columnconfigure(0, weight=1)
        
        self.mod_detail_frame = ctk.CTkScrollableFrame(mod_tab, fg_color="#1e1e1e")
        self.mod_detail_frame.grid_columnconfigure(0, weight=1)
        
        # Initial trending fetch
        threading.Thread(target=self.search_modrinth, args=("",), daemon=True).start()

        # === INSTALLED CONTENT TAB ===
        installed_tab = tabview.tab("Installed Content")
        installed_tab.grid_columnconfigure(0, weight=1)
        installed_tab.grid_rowconfigure(1, weight=1)
        
        self.installed_top_frame = ctk.CTkFrame(installed_tab, fg_color="transparent")
        self.installed_top_frame.grid(row=0, column=0, sticky="ew", pady=5)
        self.installed_top_frame.grid_columnconfigure(0, weight=1)
        
        refresh_btn = ctk.CTkButton(self.installed_top_frame, text="Refresh Installed List", fg_color="#e67e22", hover_color="#d35400", command=self.load_installed_content)
        refresh_btn.grid(row=0, column=1, padx=5)
        
        self.installed_scroll = ctk.CTkScrollableFrame(installed_tab, fg_color="#1e1e1e")
        self.installed_scroll.grid(row=1, column=0, sticky="nsew", pady=5)
        self.installed_scroll.grid_columnconfigure(0, weight=1)
        
        self.load_installed_content()

    def load_installed_content(self):
        for widget in self.installed_scroll.winfo_children():
            widget.destroy()
        
        # Check if using global .minecraft
        use_global = self.config.get("use_global_minecraft", False)
        
        if use_global:
            # Use global .minecraft directory
            mine_dir = os.path.expandvars(r'%APPDATA%\.minecraft')
            ctk.CTkLabel(self.installed_scroll, text="Content for: Global .minecraft", 
                        font=ctk.CTkFont(size=14, weight="bold"), text_color="#3498db").grid(row=0, column=0, sticky="w", padx=5, pady=(5, 15))
            
            from pathlib import Path
            mods_dir = Path(mine_dir) / "mods"
            saves_dir = Path(mine_dir) / "saves"
        else:
            # Get current instance
            current_instance_id = self.config.get("current_instance")
            if not current_instance_id:
                ctk.CTkLabel(self.installed_scroll, text="No instance selected", text_color="#e74c3c").grid(row=0, column=0, pady=20)
                return
            
            instance = self.instance_manager.get_instance(current_instance_id)
            if not instance:
                ctk.CTkLabel(self.installed_scroll, text="Instance not found", text_color="#e74c3c").grid(row=0, column=0, pady=20)
                return
            
            # Show current instance name
            ctk.CTkLabel(self.installed_scroll, text=f"Content for: {instance['name']}", 
                        font=ctk.CTkFont(size=14, weight="bold"), text_color="#3498db").grid(row=0, column=0, sticky="w", padx=5, pady=(5, 15))
            
            instance_path = self.instance_manager.get_instance_path(current_instance_id)
            mods_dir = instance_path / "mods"
            saves_dir = instance_path / "saves"
        
        row_idx = 1
        import shutil
        
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
            ctk.CTkLabel(self.installed_scroll, text="Installed Mods", text_color="#3498db", font=ctk.CTkFont(weight="bold", size=16)).grid(row=row_idx, column=0, sticky="w", padx=5, pady=(10,5))
            row_idx += 1
            for f in mods_dir.iterdir():
                if f.suffix == ".jar":
                    create_item(self.installed_scroll, mods_dir, f.name, row_idx)
                    row_idx += 1
                    
        # Draw Worlds
        if saves_dir.exists() and list(saves_dir.iterdir()):
            ctk.CTkLabel(self.installed_scroll, text="Installed Worlds", text_color="#2ecc71", font=ctk.CTkFont(weight="bold", size=16)).grid(row=row_idx, column=0, sticky="w", padx=5, pady=(20,5))
            row_idx += 1
            for f in saves_dir.iterdir():
                if f.is_dir():
                    create_item(self.installed_scroll, saves_dir, f.name, row_idx)
                    row_idx += 1

    def load_visual_skin(self):
        try:
            from PIL import Image
            username = self.username_entry.get().strip() or "DRAGO"
            target_path = os.path.expandvars(rf'%APPDATA%\.minecraft\CustomSkinLoader\LocalSkin\skins\{username}.png')
            
            if os.path.exists(target_path):
                img = Image.open(target_path)
                # Crop just the face (8, 8, 16, 16) for Minecraft 64x64 skins
                face = img.crop((8, 8, 16, 16))
                
                # Resize so it looks pixel-perfect
                face = face.resize((128, 128), resample=Image.NEAREST)
                ctk_img = ctk.CTkImage(light_image=face, size=(128,128))
                
                self.skin_preview_label.configure(image=ctk_img, text="")
        except Exception:
            pass

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
        mine_dir = os.path.expandvars(r'%APPDATA%\.minecraft')
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
        is_vanilla = not any(loader in raw_version.lower() for loader in ['fabric', 'forge', 'quilt', 'neoforge'])
        
        # Update version label and warning
        self.after(0, lambda: self.mod_version_label.configure(text=f"Browsing mods for: Minecraft {target_version} (Page {offset//15 + 1})"))
        
        if is_vanilla:
            self.after(0, lambda: self.mod_loader_warning.configure(
                text="⚠️ Vanilla version - Install Fabric/Forge to use mods!",
                text_color="#e74c3c"
            ))
        else:
            self.after(0, lambda: self.mod_loader_warning.configure(text="✓ Mod loader detected", text_color="#27ae60"))
            
        def show_status(txt):
            self.after(0, lambda: ctk.CTkLabel(self.mod_results_frame, text=txt).grid(row=0, column=0, pady=20))
            
        show_status(f"Fetching Modrinth for Minecraft {target_version}...")
        
        try:
            # Setup specific query to Modrinth - Filter by Fabric and selected Version
            facets = f'[["versions:{target_version}"],["categories:fabric"]]'
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
                show_status(f"No Fabric mods found for Minecraft {target_version}.")
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
                img_widget = ctk.CTkLabel(card, text="[Icon]", width=50, height=50, fg_color="#1e1e1e", corner_radius=5)
            
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
            img_widget = ctk.CTkLabel(header_frame, text="[Icon]", width=80, height=80, fg_color="#1e1e1e", corner_radius=5)
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
        
        # Check if it's a vanilla version (no mod loader)
        is_vanilla = not any(loader in actual_version.lower() for loader in ['fabric', 'forge', 'quilt', 'neoforge'])
        
        if is_vanilla:
            # Offer to auto-install Fabric
            confirm = ctk.CTkToplevel(self)
            confirm.title("🔧 Install Fabric?")
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
                        text=f"1. Install Fabric for Minecraft {target_version}\n2. Install {project_title}\n3. Add 'Fabric {target_version}' to your version list",
                        justify="left",
                        text_color="#27ae60").pack(pady=5)
            
            ctk.CTkLabel(confirm,
                        text="This will take about 30 seconds.",
                        font=ctk.CTkFont(size=11),
                        text_color="#aaaaaa").pack(pady=5)
            
            button_frame = ctk.CTkFrame(confirm, fg_color="transparent")
            button_frame.pack(pady=20)
            
            def install_fabric_and_mod():
                confirm.destroy()
                threading.Thread(target=self._install_fabric_then_mod, 
                               args=(target_version, project_id, project_title, btn),
                               daemon=True).start()
            
            def cancel():
                confirm.destroy()
                self._update_ui_status("Mod installation cancelled", "#aaaaaa")
            
            ctk.CTkButton(button_frame, text="Yes, Install Fabric + Mod", 
                         fg_color="#27ae60", hover_color="#2ecc71",
                         command=install_fabric_and_mod, width=200).pack(side="left", padx=10)
            
            ctk.CTkButton(button_frame, text="Cancel",
                         fg_color="#555555", hover_color="#444444",
                         command=cancel, width=100).pack(side="left", padx=10)
            
            return  # Wait for user decision
        
        # If already has mod loader, proceed normally
        self._download_and_install_mod(project_id, target_version, project_title, btn)
    
    def _install_fabric_then_mod(self, mc_version, mod_project_id, mod_title, btn=None):
        """Install Fabric, then install the mod"""
        try:
            self._update_ui_status(f"Installing Fabric for MC {mc_version}...", "#3498db")
            
            # Get Fabric version info
            import requests
            fabric_meta_url = f"https://meta.fabricmc.net/v2/versions/loader/{mc_version}"
            headers = {"User-Agent": "DragoLauncher/2.0"}
            
            fabric_versions = requests.get(fabric_meta_url, headers=headers, timeout=10).json()
            
            if not fabric_versions:
                self._update_ui_status(f"No Fabric available for MC {mc_version}", "#e74c3c")
                return
            
            # Get latest stable Fabric loader
            latest_loader = fabric_versions[0]['loader']['version']
            
            # Install Fabric using minecraft-launcher-lib
            mine_dir = os.path.expandvars(r'%APPDATA%\.minecraft')
            
            self._update_ui_status(f"Downloading Fabric {latest_loader}...", "#3498db")
            
            # Install Fabric
            minecraft_launcher_lib.fabric.install_fabric(mc_version, mine_dir)
            
            self._update_ui_status(f"✓ Fabric installed! Now installing {mod_title}...", "#27ae60")
            
            # Small delay to let user see the success message
            import time
            time.sleep(1)
            
            # Now install the mod
            self._download_and_install_mod(mod_project_id, mc_version, mod_title, btn)
            
            # Refresh version dropdown to show new Fabric version
            self.after(0, self._refresh_version_dropdown)
            
        except Exception as e:
            self._update_ui_status(f"Failed to install Fabric: {e}", "#e74c3c")
            print(f"Fabric installation error: {e}")
            import traceback
            traceback.print_exc()
    
    def _download_and_install_mod(self, project_id, target_version, project_title, btn=None):
        """Download and install a mod (separated for reuse)"""
        import requests
        import shutil
        from pathlib import Path
        
        self._update_ui_status(f"Finding {project_title} for MC {target_version}...", "#f1c40f")
        
        # Check if using global .minecraft or instance system
        use_global = self.config.get("use_global_minecraft", False)
        
        if use_global:
            # Use global .minecraft directory
            mine_dir = os.path.expandvars(r'%APPDATA%\.minecraft')
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
            url = f"https://api.modrinth.com/v2/project/{project_id}/version?loaders=[\"fabric\"]&game_versions=[\"{target_version}\"]"
            headers = {"User-Agent": "DragoLauncher/1.0"}
            resp = requests.get(url, headers=headers).json()
            
            if not resp:
                self._update_ui_status(f"No version found for MC {target_version}!", "#e74c3c")
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
            mine_dir = os.path.expandvars(r'%APPDATA%\.minecraft')
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
        
        # Look for executable asset
        exe_url = None
        for asset in assets:
            if asset["name"].endswith(".exe"):
                exe_url = asset["browser_download_url"]
                break
                
        if not exe_url:
             return
             
        if messagebox.askyesno("Update Available", f"A new version ({latest_version}) is available!\nDo you want to update now?"):
            self._update_ui_status("Downloading update...", "#f39c12")
            
            def _download_and_apply():
                try:
                    # Download the new executable
                    new_exe_data = requests.get(exe_url).content
                    update_exe_path = "DragoLauncher_Update.exe"
                    
                    with open(update_exe_path, "wb") as f:
                        f.write(new_exe_data)
                        
                    # Build an updater batch script
                    bat_path = "updater.bat"
                    current_exe = os.path.basename(sys.executable)
                    
                    # If running natively as Python instead of compiled pyinstaller, just run the new exe.
                    if not getattr(sys, 'frozen', False):
                         self.after(0, lambda: self._update_ui_status("Can't auto-update python scripts.", "#e74c3c"))
                         return
                         
                    with open(bat_path, "w") as f:
                        f.write(f'''@echo off
timeout /t 2 /nobreak >nul
del "{current_exe}"
rename "DragoLauncher_Update.exe" "{current_exe}"
start "" "{current_exe}"
del "%~f0"
''')
                    import subprocess
                    subprocess.Popen(bat_path, shell=True)
                    self.after(0, self.destroy)
                except Exception as e:
                    self.after(0, lambda: self._update_ui_status("Update failed!", "#e74c3c"))
            threading.Thread(target=_download_and_apply, daemon=True).start()

    def open_settings(self):
        settings_window = ctk.CTkToplevel(self)
        settings_window.title("Settings")
        settings_window.geometry("420x400")  # Increased height
        settings_window.transient(self)
        settings_window.resizable(False, False)
        
        ctk.CTkLabel(settings_window, text="Launcher Settings", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(20, 10))
        
        # Instance Mode Toggle
        ctk.CTkLabel(settings_window, text="Game Directory Mode:", font=ctk.CTkFont(weight="bold")).pack(pady=(10, 5))
        
        use_global_var = ctk.BooleanVar(value=self.config.get("use_global_minecraft", True))
        
        mode_frame = ctk.CTkFrame(settings_window, fg_color="transparent")
        mode_frame.pack(pady=5)
        
        ctk.CTkRadioButton(mode_frame, text="Use Global .minecraft (Default)", 
                          variable=use_global_var, value=True).pack(anchor="w", padx=20, pady=2)
        ctk.CTkRadioButton(mode_frame, text="Use Instance System (Advanced)", 
                          variable=use_global_var, value=False).pack(anchor="w", padx=20, pady=2)
        
        ctk.CTkLabel(settings_window, text="⚠️ Changing mode requires restart", 
                    text_color="#f1c40f", font=ctk.CTkFont(size=10)).pack(pady=5)
        
        # Get Max RAM dynamically via built-in Windows API
        max_ram = 16
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

        max_ram = max(2, max_ram) # Ensure slider has a safe minimum bound

        # Memory Slider (only for global mode)
        ctk.CTkLabel(settings_window, text=f"Default RAM (Global Mode Only):", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 0))
        ctk.CTkLabel(settings_window, text=f"Max: {max_ram} GB", font=ctk.CTkFont(size=10), text_color="#aaaaaa").pack()
        
        current_mem = float(self.config.get("memory", 6))
        if current_mem > max_ram:
            current_mem = float(max_ram)
            
        mem_var = ctk.DoubleVar(value=current_mem)
        
        mem_label = ctk.CTkLabel(settings_window, text=f"{int(current_mem)} GB", font=ctk.CTkFont(weight="bold"))
        
        def update_mem_label(val):
            mem_label.configure(text=f"{int(val)} GB")
            
        steps = max(1, max_ram - 2)
        mem_slider = ctk.CTkSlider(settings_window, from_=2, to=max_ram, number_of_steps=steps, variable=mem_var, command=update_mem_label)
        mem_slider.pack(pady=10)
        mem_label.pack()
        
        def save_settings():
            new_mem = int(mem_var.get())
            self.config["memory"] = new_mem
            self.config["use_global_minecraft"] = use_global_var.get()
            try:
                with open(self.config_file, "w") as f:
                    json.dump(self.config, f)
            except Exception: pass
            settings_window.destroy()
            
            # Show restart message if mode changed
            if use_global_var.get() != self.config.get("use_global_minecraft"):
                self._update_ui_status("Please restart launcher for mode change", "#f1c40f")

        save_btn = ctk.CTkButton(settings_window, text="Save Settings", fg_color="#27ae60", hover_color="#2ecc71", command=save_settings)
        save_btn.pack(pady=20)

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
            
            ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=16, weight="bold"), text_color="#3a7ebf").grid(row=0, column=0, sticky="w", padx=15, pady=(15, 5))
            
            # Clean html tags from text minimally and truncate if too long
            clean_text = text.replace("<p>", "").replace("</p>", "").replace("<b>", "").replace("</b>", "")
            if len(clean_text) > 300:
                clean_text = clean_text[:297] + "..."
                
            ctk.CTkLabel(card, text=clean_text, wraplength=600, justify="left").grid(row=1, column=0, sticky="w", padx=15, pady=(0, 15))

    def setup_bottom_bar(self):
        # Bottom Control Bar
        self.bottom_bar = ctk.CTkFrame(self, height=100, corner_radius=0, fg_color="#1e1e1e")
        self.bottom_bar.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self.bottom_bar.grid_columnconfigure(4, weight=1) # Spacer

        # Username
        self.username_entry = ctk.CTkEntry(self.bottom_bar, placeholder_text="Username", width=150)
        self.username_entry.insert(0, "DRAGO")
        self.username_entry.grid(row=0, column=0, padx=(20, 10), pady=10)

        # Dynamically fetch versions (Both installed and available online)
        mine_dir = os.path.expandvars(r'%APPDATA%\.minecraft')
        installed_versions = []
        
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

        # Big Play Button (Green/Yellow)
        self.play_button = ctk.CTkButton(self.bottom_bar, text="ENTER THE GAME", 
                                        font=ctk.CTkFont(size=16, weight="bold"),
                                        fg_color="#27ae60", hover_color="#2ecc71", 
                                        height=40, width=200,
                                        command=self.start_launch_thread)
        self.play_button.grid(row=0, column=5, padx=20, pady=10, sticky="e")
        
        # Update play button text with instance name
        self.update_play_button_text()
    
    def update_play_button_text(self):
        """Update play button text"""
        self.play_button.configure(text="▶ PLAY")

    def set_gpu_preference(self, java_path):
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
        self.dropdown_window.attributes("-topmost", True)
        
        # Get absolute position of the button
        x = self.version_button.winfo_rootx()
        y = self.version_button.winfo_rooty() - 300 # Show above the bar
        
        self.dropdown_window.geometry(f"200x300+{x}+{y}")
        
        # Scrollable frame for versions
        scroll_frame = ctk.CTkScrollableFrame(self.dropdown_window, width=200, height=300, fg_color="#1e1e1e", corner_radius=0)
        scroll_frame.pack(fill="both", expand=True)
        
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
            # Use the original global .minecraft directory
            mine_dir = os.path.expandvars(r'%APPDATA%\.minecraft')
        else:
            # Get current instance
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
                "uuid": current_uuid,
                "token": "FML",
                "jvmArguments": jvm_args,
                "launcher_name": "minecraft-launcher",
                "launcher_version": "3.32.9",
                "userType": "mojang" if is_legacy else "msa",
                "versionType": "release",
                "demo": False
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

            # Use instance-specific or detected Java path
            if use_global:
                java_path = minecraft_launcher_lib.utils.get_java_executable()
            else:
                java_path = instance['settings'].get('java_path') or minecraft_launcher_lib.utils.get_java_executable()
            
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

            process = subprocess.Popen(command)
            
            # Process Priority (High = 0x00000080)
            # CAUTION: We REMOVED the CPU Affinity mask (0x0F) because forcing Minecraft 
            # to only use 4 cores severely chokes chunk rendering and world generation.
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
            self._update_ui_status("Ready to play", "#aaaaaa")

        except Exception as e:
            self._update_ui_status("Launch Error!", "#e74c3c")
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            self.play_button.configure(state="normal")
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
            mine_dir = os.path.expandvars(r'%APPDATA%\.minecraft')
            # This built-in library automatically checks every file signature and downloads missing ones
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
            
        mine_dir = os.path.expandvars(r'%APPDATA%\.minecraft')
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