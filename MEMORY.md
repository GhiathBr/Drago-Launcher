# Drago Launcher — Project Memory

> **For AI agents:** Read this file **before** re-exploring the whole codebase. Use `ERRORS.md` for known bugs and regression history. Only deep-dive into source when this doc is insufficient or stale.

**Last audited:** 2026-06-07  
**App version in code:** `v2.1.0` (see `luncher.py` → `CURRENT_VERSION`; git history mentions v2.2.0 — may be out of sync)

---

## What This Project Is

**Drago Launcher** is a desktop Minecraft launcher built with **CustomTkinter** (Python). It supports:

- Global `%APPDATA%\.minecraft` mode **or** isolated per-instance directories
- Vanilla + mod loaders (Fabric, Forge, Quilt, NeoForge)
- Microsoft device-code login (online play)
- Modrinth browsing (mods, worlds/modpacks, shaders)
- Skin management via CustomSkinLoader + NameMC curated skins
- Instance CRUD, backups, modpack import (.mrpack), conflict scanning, crash analysis
- OptiFine auto-download/install, portable mode, auto-updater (frozen exe only)
- 7 UI themes via `theme_manager.py`

**Entry point:** `luncher.py` → `DragoLauncher` class → `app.mainloop()`

---

## File Map (17 Python files)

| File | Role |
|------|------|
| `luncher.py` | **Main app** (~3270 lines). All UI pages, launch logic, settings, Modrinth, OptiFine, MS login. Monolithic. |
| `instance_manager.py` | Instance CRUD, metadata in `instances.json`, per-instance folder tree |
| `portable.py` | Portable mode detection (`.portable_mode` marker), path resolution |
| `auth.py` | `XSTSIdentityManager` — OAuth device flow → XBL → XSTS → Minecraft profile |
| `loader_installer.py` | Fetch/install Fabric, Forge, Quilt, NeoForge |
| `java_manager.py` | Scan Java installs (registry, env, PATH), MC version → Java mapping |
| `backup_manager.py` | Pre-launch backups, restore, cleanup |
| `theme_manager.py` | 7 themes; custom CTK JSON for purple/amber accents |
| `console_viewer.py` | Live game stdout/stderr window |
| `modpack_manager.py` | Import/export Modrinth `.mrpack` |
| `mineskin_browser.py` | Curated NameMC skins, Mojang UUID lookup, CustomSkinLoader apply |
| `shader_manager.py` | Known shader packs from GitHub, install to shaderpacks |
| `conflict_scanner.py` | Mod duplicate/incompatibility detection |
| `crash_analyzer.py` | Parse crash reports, pattern-match known errors |
| `network_monitor.py` | Poll Mojang news URL; refresh on reconnect |
| `fix_skins_layout.py` | One-off migration script (references missing `skins_tab_vertical.txt`) |

**No `requirements.txt`** in repo. Dependencies inferred from imports:

```
customtkinter, minecraft-launcher-lib, requests, aiohttp, packaging, Pillow
optional: tkinterdnd2
```

---

## Directory & Config Layout

### Standard (non-portable) mode

| Path | Purpose |
|------|---------|
| `%APPDATA%\.minecraft` | Game files (global mode) |
| `%APPDATA%\.drago_launcher\` | Launcher data root |
| `%APPDATA%\.drago_launcher\instances\` | Instance folders (UUID dirs) |
| `%APPDATA%\.drago_launcher\instances.json` | Instance metadata |
| `%APPDATA%\.drago_launcher\backups\` | Backup index + data |
| `%APPDATA%\.minecraft\drago_launcher_config.json` | Launcher config (global mode) |

### Portable mode

Triggered by `.portable_mode` file or `portable_mode: true` in config.

| Path | Purpose |
|------|---------|
| `<launcher_dir>\.minecraft` | Game files |
| `<launcher_dir>\data\` | Instance manager base |
| `<launcher_dir>\drago_launcher_config.json` | Config |

### Instance folder structure

Each instance (`instances/<uuid>/`) contains: `mods`, `saves`, `resourcepacks`, `shaderpacks`, `config`, `logs`, `screenshots`, `crash-reports`

### Config keys (`drago_launcher_config.json`)

```json
{
  "last_version": "",
  "memory": 6,
  "current_instance": null,
  "use_global_minecraft": true,
  "theme": "Drago Dark (Default)",
  "safe_mode": false,
  "show_console": true,
  "ssl_verify": false,
  "portable_mode": false,
  "auto_backup": true,
  "uuid": ""
}
```

---

## Architecture Overview

```
luncher.py (DragoLauncher)
├── Sidebar: Home | Instances | Content Browser | Updates | Import Modpack | Settings
├── Page container (swap views)
│   ├── main_frame        → Mojang news feed
│   ├── content_browser   → Tabview: Skins | Modrinth Mods | Worlds | Shaders | Installed
│   └── instances_frame   → Instance cards
└── bottom_bar            → Username, MS Login, Version dropdown, Play
```

**Threading pattern:** Network/launch/auth run in `threading.Thread(daemon=True)`. UI updates via `self.after(0, callback)`.

**Launch flow** (`launch_thread`):
1. Resolve `mine_dir` (global vs instance)
2. Optional safe mode (temporarily move mods/shaders/resourcepacks)
3. Optional auto-backup
4. Download version if missing (`minecraft_launcher_lib.install`)
5. OptiFine special path if version contains "OptiFine"
6. Build JVM args (G1GC, CustomSkinLoader, 1.16.5 auth bypass)
7. `minecraft_launcher_lib.command.get_minecraft_command()`
8. 1.16.5 auth arg cleanup
9. Java path from instance settings or `suggest_java_for_instance()`
10. `subprocess.Popen` + optional `spawn_console()`
11. Restore safe mode files after exit

---

## Key Modules — Quick API Reference

### `auth.XSTSIdentityManager`
- `start_device_authorization()` → device code dict
- `poll_device_authorization(device_code, interval)` → `OAuthTokens`
- `get_minecraft_profile(oauth)` → `(mc_access_token, profile_dict)`
- Client ID hardcoded: `ab5dd215-1a94-4383-a5f2-d51d42ab758f`

### `instance_manager.InstanceManager`
- `create_instance(name, version, loader, loader_version)`
- `get_instance_path(id)`, `update_instance_settings`, `duplicate`, `export`, `import`
- Metadata in `base_dir/instances.json` (NOT per-instance `instance.json` for native instances — that's only for imports)

### `loader_installer`
- `get_loader_versions(loader, mc_version)` → list of dicts
- `install_loader(loader, mc_version, loader_version, minecraft_dir, progress_callback)`
- `AVAILABLE_LOADERS = ["vanilla", "fabric", "forge", "quilt", "neoforge"]`

### `java_manager`
- `get_java_for_mc_version("1.21.1")` → 21
- `scan_java_installations()` → list of `{path, version, vendor, source}`
- `suggest_java_for_instance(java_list, mc_version)` → best path

### `theme_manager`
- `THEMES` dict with `appearance`, `color`, UI accent hex values
- `apply_theme(name)` — built-in CTK colors or generated JSON in `%TEMP%\drago_ctk_themes\`
- Purple/Amber need custom theme JSON (not built-in CTK colors)

### `mineskin_browser`
- `search_skins(query)` / `get_trending_skins()` — **curated static list**, not live API
- `apply_skin_from_mineskin(skin_id, username, minecraft_dir)` → writes to CustomSkinLoader

### `conflict_scanner` / `crash_analyzer`
- `scan_mods_directory(path)` → issues list
- `analyze_instance(instance_dir)` → up to 10 crash report analyses

---

## External APIs & URLs

| Service | Used For |
|---------|----------|
| `launchercontent.mojang.com/news.json` | News feed + network monitor |
| `piston-meta.mojang.com` (via minecraft-launcher-lib) | Version list, installs |
| `api.modrinth.com/v2/search` | Mod/world/shader browser |
| `meta.fabricmc.net`, `files.minecraftforge.net`, `meta.quiltmc.org`, `api.neoforged.net` | Loader versions |
| `api.github.com/repos/GhiathBr/Drago-Launcher/releases/latest` | Self-update |
| `optifine.net/downloads` | OptiFine version scrape |
| `login.microsoftonline.com` (device code) | MS auth |
| `api.minecraftservices.com` | MC profile |
| `api.mojang.com/users/profiles/minecraft/` | Username → UUID |
| `s.namemc.com` | Skin images |
| `api.adoptium.net` | Java download URLs (java_manager) |

---

## Environment & Security

- **`DRAGO_SSL_VERIFY=1`** — enables SSL verification (default off; patches `requests.Session` globally)
- SSL disabled by default for antivirus/firewall compatibility
- MS Client ID is public (standard for desktop OAuth)
- Offline play: username defaults to "DRAGO", token "FML", generated UUID in config

---

## UI Pages Detail

### Content Browser tabs
1. **Skins** — left: preview/upload; right: curated skin list (vertical layout, rewritten in v2.2)
2. **Modrinth Mods** — searches with `versions:{mc}` + `categories:{loader}` facets
3. **Modrinth Worlds** — modpack type with map/adventure categories
4. **Shaders** — Modrinth shader search + `shader_manager` known shaders
5. **Installed Content** — lists mods/RPs/shaders; conflict scan + crash report buttons

### Settings dialog
Theme, global vs instance mode, RAM slider, console toggle, auto-backup, SSL verify, portable mode, Java rescan, backup cleanup.

**Restart required** for: instance mode change, portable mode toggle.

---

## Version Dropdown Logic

- Installed versions shown first with friendly names (reads `inheritsFrom` in version JSON)
- Online releases filtered by regex: `^(1\.\d+(\.\d+)?|2[6-9]\.\d+(\.\d+)?)$`
- OptiFine versions scraped and inserted above matching vanilla version
- `version_id_to_display` maps friendly name → actual version folder ID

---

## Git / Repo Notes

- `.gitignore` ignores everything except `*.py`, `.gitignore`, `MEMORY.md`, `ERRORS.md`
- No tests directory tracked (tests/ ignored)
- `fix_skins_layout.py` is a leftover one-shot script

---

## Common Tasks — Where to Look

| Task | Go to |
|------|-------|
| Change launch JVM args | `luncher.py` → `launch_thread` (~line 3030) |
| Add a theme | `theme_manager.py` → `THEMES` + maybe `_ACCENT_OVERRIDES` |
| Add mod incompatibility | `conflict_scanner.py` → `KNOWN_INCOMPATIBILITIES` |
| Add crash pattern | `crash_analyzer.py` → `KNOWN_CRASH_PATTERNS` |
| New loader support | `loader_installer.py` + `AVAILABLE_LOADERS` + instance create dialog |
| Fix Modrinth search | `luncher.py` → `search_modrinth` (~line 1553) |
| MS login flow | `luncher.py` → `_microsoft_login_thread` + `auth.py` |
| Instance settings UI | `luncher.py` → `open_instance_settings` |

---

## Maintenance

- **Update this file** when adding major features, changing paths, or restructuring modules.
- **Update `ERRORS.md`** whenever a bug is fixed — include root cause and what NOT to do again.
- If this doc and code disagree, **trust the code** and fix this doc.
