import customtkinter as ctk
import minecraft_launcher_lib
import subprocess
import os
import sys
import threading
import json

# --- APP SETUP ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class DragoLauncher(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Drago Launcher - Safe & Clear")
        self.geometry("900x600")
        self.minsize(800, 500)
        
        # Load Config globally
        self.config_file = "drago_launcher_config.json"
        self.config = {"last_version": "", "memory": 6}
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    self.config.update(json.load(f))
            except Exception:
                pass

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
        
        # Show News by default
        self.show_news_page()

    def show_news_page(self):
        self.content_browser_frame.grid_forget()
        self.main_frame.grid(row=0, column=0, sticky="nsew")
        
    def show_content_page(self):
        self.main_frame.grid_forget()
        self.content_browser_frame.grid(row=0, column=0, sticky="nsew")

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

        self.btn_mods = ctk.CTkButton(self.sidebar_frame, text="Game Content Browser", fg_color="#1f538d", anchor="w", command=self.show_content_page)
        self.btn_mods.grid(row=3, column=0, padx=20, pady=10)

        self.btn_settings = ctk.CTkButton(self.sidebar_frame, text="Settings", fg_color="#1f538d", anchor="w", command=self.open_settings)
        self.btn_settings.grid(row=5, column=0, padx=20, pady=20)

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
        mod_tab.grid_rowconfigure(1, weight=1)
        
        self.search_frame = ctk.CTkFrame(mod_tab, fg_color="transparent")
        self.search_frame.grid(row=0, column=0, sticky="ew", pady=5)
        self.search_frame.grid_columnconfigure(0, weight=1)
        
        self.mod_search_entry = ctk.CTkEntry(self.search_frame, placeholder_text="Search Mods or Modpacks...")
        self.mod_search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        
        search_btn = ctk.CTkButton(self.search_frame, text="Search", width=80, command=lambda: threading.Thread(target=self.search_modrinth).start())
        search_btn.grid(row=0, column=1)
        
        self.mod_results_frame = ctk.CTkScrollableFrame(mod_tab, fg_color="#1e1e1e")
        self.mod_results_frame.grid(row=1, column=0, sticky="nsew", pady=5)
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
            
        mine_dir = os.path.expandvars(r'%APPDATA%\.minecraft')
        mods_dir = os.path.join(mine_dir, "mods")
        saves_dir = os.path.join(mine_dir, "saves")
        
        row_idx = 0
        import shutil
        
        def create_item(parent, base_dir, filename, idx):
            item_frame = ctk.CTkFrame(parent, fg_color="#2b2b2b", corner_radius=5)
            item_frame.grid(row=idx, column=0, sticky="ew", pady=3, padx=5)
            item_frame.grid_columnconfigure(0, weight=1)
            
            ctk.CTkLabel(item_frame, text=filename, font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", padx=10, pady=5)
            
            def delete_item():
                target = os.path.join(base_dir, filename)
                try:
                    if os.path.isdir(target):
                        shutil.rmtree(target)
                    else:
                        os.remove(target)
                    item_frame.destroy()
                except Exception as e:
                    print(f"Delete Error: {e}")
                    
            del_btn = ctk.CTkButton(item_frame, text="Delete", width=60, fg_color="#c0392b", hover_color="#e74c3c", command=delete_item)
            del_btn.grid(row=0, column=1, padx=10, pady=5)

        # Draw Mods
        if os.path.exists(mods_dir) and os.listdir(mods_dir):
            ctk.CTkLabel(self.installed_scroll, text="Installed Mods", text_color="#3498db", font=ctk.CTkFont(weight="bold", size=16)).grid(row=row_idx, column=0, sticky="w", padx=5, pady=(10,5))
            row_idx += 1
            for f in os.listdir(mods_dir):
                if f.endswith(".jar"):
                    create_item(self.installed_scroll, mods_dir, f, row_idx)
                    row_idx += 1
                    
        # Draw Worlds
        if os.path.exists(saves_dir) and os.listdir(saves_dir):
            ctk.CTkLabel(self.installed_scroll, text="Installed Worlds", text_color="#2ecc71", font=ctk.CTkFont(weight="bold", size=16)).grid(row=row_idx, column=0, sticky="w", padx=5, pady=(20,5))
            row_idx += 1
            for f in os.listdir(saves_dir):
                full_path = os.path.join(saves_dir, f)
                if os.path.isdir(full_path):
                    create_item(self.installed_scroll, saves_dir, f, row_idx)
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

    def search_modrinth(self, init_query=None):
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
        
        raw_version = self.version_var.get()
        target_version = "1.21.1" # Fallback
        # Safely extract pure Minecraft version by taking everything after the last dash
        # e.g., 'fabric-loader-0.19.2-1.21.2' -> '1.21.2'
        if "-" in raw_version:
            target_version = raw_version.split("-")[-1]
        elif re.match(r'^\d+\.\d+(?:\.\d+)?$', raw_version):
            target_version = raw_version
            
        def show_status(txt):
            self.after(0, lambda: ctk.CTkLabel(self.mod_results_frame, text=txt).grid(row=0, column=0, pady=20))
            
        show_status(f"Fetching Modrinth for Minecraft {target_version}...")
        
        try:
            # Setup specific query to Modrinth - Filter by Fabric and selected Version
            facets = f'[["versions:{target_version}"],["categories:fabric"]]'
            encoded_facets = urllib.parse.quote(facets)
            url = f"https://api.modrinth.com/v2/search?limit=15&facets={encoded_facets}"
            if query:
                url += f"&query={urllib.parse.quote(query)}"
            else:
                url += "&index=downloads" # Fetch trending if blank search
                
            headers = {"User-Agent": "DragoLauncher/1.0"}
            resp = requests.get(url, headers=headers).json()
            
            self.after(0, clear_widgets)
                
            hits = resp.get("hits", [])
            if not hits:
                show_status(f"No Fabric mods found for {target_version}.")
                return
            
            # Prefetch icons in background thread to avoid freezing UI
            from PIL import Image
            import io
            for mod in hits:
                mod['pil_image'] = None
                if mod.get('icon_url'):
                    try:
                        img_data = requests.get(mod['icon_url'], timeout=3).content
                        mod['pil_image'] = Image.open(io.BytesIO(img_data)).resize((50, 50), Image.LANCZOS)
                    except Exception:
                        pass
                
            # Safely render results onto UI
            self.after(0, self.render_mod_results, hits, target_version)
                
        except Exception as e:
            self.after(0, clear_widgets)
            show_status(f"Error connecting to Modrinth:\n{e}")

    def render_mod_results(self, hits, target_version):
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
            
            btn = ctk.CTkButton(card, text="Install\nMod", width=70, fg_color="#1f538d", hover_color="#2980b9",
                                command=lambda m_id=mod["project_id"], m_title=mod["title"]: threading.Thread(target=self.install_modrinth_mod, args=(m_id, target_version, m_title)).start())
            btn.grid(row=0, column=3, rowspan=2, padx=10, pady=10)

    def show_mod_details(self, mod, target_version):
        self.search_frame.grid_forget()
        self.mod_results_frame.grid_forget()
        
        for widget in self.mod_detail_frame.winfo_children():
            widget.destroy()
            
        self.mod_detail_frame.grid(row=0, column=0, rowspan=2, sticky="nsew", pady=5)
        
        def go_back():
            self.mod_detail_frame.grid_forget()
            self.search_frame.grid(row=0, column=0, sticky="ew", pady=5)
            self.mod_results_frame.grid(row=1, column=0, sticky="nsew", pady=5)
            
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
        
        install_btn = ctk.CTkButton(header_frame, text="Install Mod", fg_color="#27ae60", hover_color="#2ecc71", font=ctk.CTkFont(weight="bold"),
                                    command=lambda: threading.Thread(target=self.install_modrinth_mod, args=(mod["project_id"], target_version, mod["title"])).start())
        install_btn.grid(row=0, column=2, rowspan=2, padx=20, sticky="e")
        header_frame.grid_columnconfigure(1, weight=1)
        
        desc_frame = ctk.CTkFrame(self.mod_detail_frame, fg_color="#2b2b2b")
        desc_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
        
        desc_label = ctk.CTkLabel(desc_frame, text=mod["description"] + "\n\nFetching complete description...", wraplength=650, justify="left", font=ctk.CTkFont(size=14))
        desc_label.pack(padx=20, pady=20, anchor="w", fill="x", expand=True)

        def fetch_full_info():
            import requests
            import re
            try:
                # Query the specific project endpoint to get the giant "body" description
                resp = requests.get(f"https://api.modrinth.com/v2/project/{mod['project_id']}", headers={"User-Agent": "DragoLauncher/1.0"}, timeout=5).json()
                body = resp.get("body", "")
                if body:
                    # Clean up html and basic markdown headers so it reads cleaner in a UI label
                    body = re.sub(r'<[^>]+>', '', body)
                    body = re.sub(r'#+\s+', '', body)
                    
                    # Limit the string size so Tkinter doesn't freeze on gigantic mod pages
                    if len(body) > 12000:
                        body = body[:12000] + "...\n\n[Description Truncated due to length - Install to play!]"
                    
                    self.after(0, lambda: desc_label.configure(text=body))
            except Exception:
                pass
                
        threading.Thread(target=fetch_full_info, daemon=True).start()

    def install_modrinth_mod(self, project_id, target_version, project_title):
        import requests
        import shutil
        self._update_ui_status(f"Finding match for {project_title}...", "#f1c40f")
        try:
            # Query the specific version required
            url = f"https://api.modrinth.com/v2/project/{project_id}/version?loaders=[\"fabric\"]&game_versions=[\"{target_version}\"]"
            headers = {"User-Agent": "DragoLauncher/1.0"}
            resp = requests.get(url, headers=headers).json()
            
            if not resp:
                self._update_ui_status("Mod version missing!", "#e74c3c")
                return
                
            # Get latest matching file
            file_data = resp[0]["files"][0]
            download_url = file_data["url"]
            filename = file_data["filename"]
            
            mine_dir = os.path.expandvars(r'%APPDATA%\.minecraft')
            mods_dir = os.path.join(mine_dir, "mods")
            os.makedirs(mods_dir, exist_ok=True)
            target_path = os.path.join(mods_dir, filename)
            
            self._update_ui_status(f"Downloading {project_title}...", "#3498db")
            
            # File download
            with requests.get(download_url, stream=True) as r:
                with open(target_path, 'wb') as f:
                    shutil.copyfileobj(r.raw, f)
            
            self._update_ui_status(f"Installed {project_title}!", "#27ae60")
        except Exception as e:
            self._update_ui_status(f"Failed installing Mod", "#e74c3c")
            print(f"Mod Install Error: {e}")

    def open_settings(self):
        settings_window = ctk.CTkToplevel(self)
        settings_window.title("Settings")
        settings_window.geometry("350x250")
        settings_window.transient(self)
        
        ctk.CTkLabel(settings_window, text="Launcher Settings", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(20, 10))
        
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

        # Memory Slider
        ctk.CTkLabel(settings_window, text=f"RAM Allocation (Max: {max_ram} GB):").pack(pady=(10, 0))
        
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
            try:
                with open(self.config_file, "w") as f:
                    json.dump(self.config, f)
            except Exception: pass
            settings_window.destroy()

        save_btn = ctk.CTkButton(settings_window, text="Save Settings", fg_color="#27ae60", hover_color="#2ecc71", command=save_settings)
        save_btn.pack(pady=15)

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
            for v in minecraft_launcher_lib.utils.get_version_list():
                if v['type'] == 'release': # We filter to releases to avoid cluttering with 1000+ snapshots
                    all_versions.append(v['id'])
        except Exception:
            all_versions = ["1.21.1", "1.20.4", "1.19.4"] # Fallback if no internet

        self.installed_versions_cache = installed_versions
        dropdown_values = []
        
        # Add installed versions first (raw strings)
        for iv in installed_versions:
            if iv not in dropdown_values:
                dropdown_values.append(iv)
            
        # Add online versions that aren't installed yet
        for v in all_versions:
            if v not in installed_versions and v not in dropdown_values:
                dropdown_values.append(v)
                
        if not dropdown_values:
            dropdown_values = ["No versions found"]

        # Memory / Remember last selection
        saved_version = dropdown_values[0]
        if self.config.get("last_version") in dropdown_values:
            saved_version = self.config["last_version"]

        # Custom Version Dropdown (Scrollable)
        self.version_var = ctk.StringVar(value=saved_version)
        self.dropdown_values = dropdown_values
        
        self.version_button = ctk.CTkButton(self.bottom_bar, textvariable=self.version_var, 
                                            width=200, fg_color="#2b2b2b", hover_color="#3a3a3a", 
                                            anchor="w", command=self.open_version_dropdown)
        self.version_button.grid(row=0, column=1, padx=10, pady=10)

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

    def get_rtx3050_jvm_args(self):
        # Dynamically fetch user RAM allocation
        ram = int(self.config.get("memory", 6))
        
        # Optimized Garbage Collection for modern Java/Minecraft
        return [
            f"-Xmx{ram}G",
            f"-Xms{ram}G",
            "-XX:+UnlockExperimentalVMOptions",
            "-XX:+UseG1GC",
            "-XX:G1NewSizePercent=20",
            "-XX:G1ReservePercent=20",
            "-XX:MaxGCPauseMillis=50",
            "-XX:G1HeapRegionSize=32M",
            "-Dcustomskinloader.enabled=true" # CustomSkinLoader property toggle flag
        ]

    def _update_ui_status(self, text, color):
        self.status_label.configure(text=text, text_color=color)

    def _install_progress_callback(self, current, max_val):
        # Calculate percentage
        if max_val > 0:
            percentage = current / max_val
            self.progress_bar.set(percentage)
            
    def start_launch_thread(self):
        threading.Thread(target=self.launch_game, daemon=True).start()

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
            
            # Save to config memory
            self.config["last_version"] = v
            try:
                with open(self.config_file, "w") as f:
                    json.dump(self.config, f)
            except:
                pass
            
        for v in self.dropdown_values:
            # Highlight installed versions! Bright white bold for installed, dimmer gray for uninstalled
            if v in self.installed_versions_cache:
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

    def launch_game(self):
        self._update_ui_status("Initializing...", "#f1c40f")
        self.play_button.configure(state="disabled")
        
        # Configuration
        mine_dir = os.path.expandvars(r'%APPDATA%\.minecraft')
        name = self.username_entry.get().strip()
        
        version = self.version_var.get()

        if not version or version == "No versions found":
            self._update_ui_status("No version selected!", "#e74c3c")
            self.play_button.configure(state="normal")
            return

        # Check if version is installed, if not, install it!
        raw_installed = []
        if os.path.exists(mine_dir):
            try:
                raw_installed = [v['id'] for v in minecraft_launcher_lib.utils.get_installed_versions(mine_dir)]
            except: pass
            
        if version not in raw_installed:
            self._update_ui_status(f"Downloading {version}...", "#3498db")
            self.progress_bar.pack(anchor="w", pady=(5,0)) # Show progress bar
            self.progress_bar.set(0)
            
            # Setup Callbacks for installation
            current_max = 0
            def set_max(val):
                nonlocal current_max
                current_max = val
                
            def set_progress(val):
                self._install_progress_callback(val, current_max)
                
            def set_status(val):
                # Using update_idletasks might be needed, but configure is usually okay.
                self._update_ui_status(f"Installing: {val}", "#3498db")

            callback = {
                "setStatus": set_status,
                "setProgress": set_progress,
                "setMax": set_max
            }
            
            try:
                minecraft_launcher_lib.install.install_minecraft_version(version, mine_dir, callback=callback)
                self._update_ui_status("Download Complete!", "#27ae60")
            except Exception as e:
                self._update_ui_status("Download Failed!", "#e74c3c")
                print(f"Install Error: {e}")
                self.progress_bar.pack_forget()
                self.play_button.configure(state="normal")
                return
                
            # Hide progress bar after success
            self.progress_bar.pack_forget()

        self._update_ui_status("Launching Game...", "#f1c40f")

        options = {
            "username": name,
            "uuid": "",
            "token": "",
            "jvmArguments": self.get_rtx3050_jvm_args()
        }

        # Launch Logic
        try:
            command = minecraft_launcher_lib.command.get_minecraft_command(version, mine_dir, options)
            java_path = r"C:\Program Files\Java\jdk-26.0.1\bin\java.exe"
            if os.path.exists(java_path):
                command[0] = java_path
            
            self._update_ui_status("Game Running!", "#27ae60")
            
            # Run the game and WAIT for it to close
            process = subprocess.Popen(command, cwd=mine_dir)
            process.wait()
            
            # Game closed
            if process.returncode == 0:
                self._update_ui_status("Game Closed", "#aaaaaa")
            else:
                self._update_ui_status(f"Game Crashed (Code {process.returncode})", "#e74c3c")
                
        except Exception as e:
            self._update_ui_status("Launch Failed (See Terminal)", "#e74c3c")
            print(f"Launch Error Detail:\n{e}")
        finally:
            self.play_button.configure(state="normal")
            
if __name__ == "__main__":
    app = DragoLauncher()
    app.mainloop()