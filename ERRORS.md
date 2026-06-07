# Drago Launcher — Error & Regression Log

> **For AI agents:** Check this file before fixing bugs. When you fix a bug, **add an entry here** so we don't reintroduce it. Format entries with status: `OPEN`, `FIXED`, or `WONTFIX`.

**Last updated:** 2026-06-07

---

## How to Log a Fix

```markdown
### [FIXED] Short title (YYYY-MM-DD)
- **Symptom:** What the user saw
- **Root cause:** Why it happened
- **Fix:** What changed (file + approach)
- **Do NOT:** Specific things that would re-break it
```

---

## Open Issues

### [OPEN] `loader_installer.py` missing `import requests`
- **Symptom:** `NameError: name 'requests' is not defined` when fetching Fabric/Forge/Quilt/NeoForge versions or downloading installers
- **Root cause:** File uses `requests.get()` throughout but only imports `urllib.request`
- **Fix needed:** Add `import requests` at top
- **Do NOT:** Assume loader version fetch works without testing; the import is genuinely missing

### [OPEN] `installed_versions` undefined if `.minecraft` missing
- **Symptom:** `NameError` on first launch when `%APPDATA%\.minecraft` doesn't exist
- **Root cause:** `setup_bottom_bar()` only sets `installed_versions` inside `if os.path.exists(mine_dir)` but uses it unconditionally at line ~2621
- **Fix needed:** Initialize `installed_versions = []` before the `if` block
- **Do NOT:** Remove the initialization when refactoring version dropdown code

### [OPEN] Settings "restart required" for mode change never triggers
- **Symptom:** Switching global ↔ instance mode saves but never warns to restart
- **Root cause:** In `save_settings()`, `self.config["use_global_minecraft"]` is updated **before** `changed_mode` is computed, so comparison is always equal
- **Fix needed:** Capture `old_mode = self.config.get("use_global_minecraft")` before assignment
- **Do NOT:** Compare after overwriting config value

### [OPEN] `CURRENT_VERSION` out of sync with releases
- **Symptom:** Updater may not prompt when new release exists (or prompts incorrectly)
- **Root cause:** Code says `v2.1.0`, git commit message says `v2.2.0`
- **Fix needed:** Bump `CURRENT_VERSION` in `luncher.py` to match releases
- **Do NOT:** Forget to update version string when tagging releases

### [OPEN] Forge installer uses `--installServer` flag
- **Symptom:** Forge may fail to install correctly for client play
- **Root cause:** `_install_forge()` passes `--installServer` instead of `--installClient`
- **Location:** `loader_installer.py` ~line 200
- **Do NOT:** Copy server install flags for client launcher use without verifying

### [OPEN] NeoForge installer uses `--install-server` flag
- **Symptom:** Similar to Forge — may install server profile instead of client
- **Location:** `loader_installer.py` ~line 279
- **Do NOT:** Assume headless installer flags match between Forge and NeoForge without checking docs

### [OPEN] `theme_manager.py` unused imports
- **Symptom:** None (lint noise only)
- **Root cause:** `shutil` and `zipfile` imported but unused in recent theme work
- **Do NOT:** Re-add complex zip logic unless actually needed for theme extraction

### [OPEN] `fix_skins_layout.py` references missing file
- **Symptom:** Script fails with "Could not find skins tab markers" or missing `skins_tab_vertical.txt`
- **Root cause:** One-shot migration script; replacement file not in repo
- **Do NOT:** Run this script — skins tab was already migrated inline in `luncher.py`

---

## Fixed Issues (Historical)

### [FIXED] Shader download fails with "No version found for MC X (fabric)" (2026-06-07)
- **Symptom:** Installing shaders from Modrinth tab failed for MC 26.1.2 Fabric with "No version found for MC 26.1.2 (fabric)!"
- **Root cause:** Shaders reused `install_modrinth_mod` → `_download_and_install_mod`, which queries Modrinth with `loaders=["fabric"]` and installs to `mods/`. Shader packs on Modrinth use `iris`/`optifine` loaders, not fabric.
- **Fix:** Added `install_modrinth_shader` + `_download_and_install_shader` — queries by `game_versions` only (fallback: iris, optifine), installs to `shaderpacks/`
- **Do NOT:** Route shader installs through `install_modrinth_mod` or filter shaders by fabric loader

### [FIXED] Amber Glow theme broken — invalid CTK color "yellow" (2026-06-07)
- **Symptom:** Amber Glow theme didn't apply correct accent colors; CTK has no "yellow" built-in theme
- **Root cause:** `THEMES["Amber Glow"]["color"]` was `"yellow"` which CustomTkinter doesn't ship
- **Fix:** Changed to `"amber"` + custom theme JSON generation via `_ACCENT_OVERRIDES` and `_build_custom_theme()` in `theme_manager.py`
- **Do NOT:** Set theme colors to non-existent CTK built-in names; check `_BUILTIN_COLORS = {"blue", "dark-blue", "green"}`

### [FIXED] Deep Purple theme needs custom CTK JSON (2026-06-07)
- **Symptom:** Purple theme colors didn't match design
- **Root cause:** CTK has no built-in "purple" color theme
- **Fix:** Same custom JSON approach as amber in `theme_manager.py`
- **Do NOT:** Call `ctk.set_default_color_theme("purple")` directly

### [FIXED] Launch thread indentation / instance management (git: e7f96a8)
- **Symptom:** Launch crashes or wrong scope for instance variables
- **Fix:** Corrected indentation in launch thread; proper instance path resolution
- **Do NOT:** Nest launch logic incorrectly inside conditionals

### [FIXED] CPU priority / Modrinth UI / launcher states (git: 66eb3b1)
- **Symptom:** UI state bugs, Modrinth display issues
- **Fix:** CPU priority logic, Modrinth UI upgrade, launcher state handling
- **Do NOT:** Regress Modrinth pagination or state sync between threads

### [FIXED] SSL settings text cutoff in Settings (luncher.py ~2425)
- **Symptom:** Long SSL description truncated in settings window
- **Fix:** Separate frame with `wraplength=380` and checkbox/label grid layout
- **Do NOT:** Put long text directly in `CTkCheckBox` text parameter

### [FIXED] News card text too dim (luncher.py ~2568)
- **Symptom:** Poor contrast on dark background for news feed
- **Fix:** Title `#60d0ff`, body `#e0e0e0`
- **Do NOT:** Use `#aaaaaa` for primary news body text

### [FIXED] Modrinth worlds tab empty/wrong results (luncher.py ~1071)
- **Symptom:** Worlds tab returned no results
- **Root cause:** Modrinth has no `world` project type; need modpacks with map/adventure categories
- **Fix:** Query modpacks with appropriate category facets
- **Do NOT:** Search `project_type:world` on Modrinth API

### [FIXED] Shader cards missing images (luncher.py ~1094)
- **Symptom:** Shader browse showed no thumbnails
- **Fix:** Use `icon_url` with fallback to `featured_gallery`
- **Do NOT:** Only check one image field from Modrinth response

### [FIXED] Modrinth card layout / clipping (luncher.py ~1005-1160)
- **Symptom:** Cards clipped at bottom, misaligned buttons, uneven descriptions
- **Fix:** `scrollbar` mode, rigid card grid, description char limit, bottom padding frame
- **Do NOT:** Use always-on scroll for results; remove bottom padding

### [FIXED] Version dropdown z-index / overlap (luncher.py ~2853)
- **Symptom:** Dropdown overlapped other UI
- **Fix:** `topmost` attribute, position above button, border styling
- **Do NOT:** Create dropdown without `topmost` on Windows

### [FIXED] Skins tab layout (git: 8a48f17 / v2.2.0)
- **Symptom:** Old horizontal skins layout was cramped
- **Fix:** Vertical two-panel layout (preview left, browser right) directly in `luncher.py`
- **Do NOT:** Re-run `fix_skins_layout.py` or revert to old horizontal-only layout

### [FIXED] 1.16.5 offline multiplayer auth bypass
- **Symptom:** 1.16.5 LAN/offline issues with modern auth
- **Fix:** JVM props pointing auth hosts to `nope.invalid` + custom `--accessToken FML` args
- **Do NOT:** Remove 1.16.5 special casing without testing offline LAN

---

## Patterns to Avoid (General)

1. **UI updates from background threads** — always use `self.after(0, ...)` for Tkinter/CTk widgets
2. **Version ID vs display name** — launch uses `version_id_to_display` mapping; breaking this causes wrong MC version launches
3. **`inheritsFrom` parsing** — modded versions (Fabric/Forge) need JSON read to get base MC version for Modrinth facets
4. **Global SSL patch** — `requests` verify=False is patched at import time unless `DRAGO_SSL_VERIFY=1`; don't fight this unintentionally
5. **Instance vs global mode** — `use_global_minecraft` completely changes `mine_dir` resolution; test both paths
6. **Safe mode file restore** — launch_thread must restore backed-up mods/shaders even on exception (already has try/except blocks — keep them)
7. **Duplicate `import os`** in `loader_installer.py` — harmless but signals file needs cleanup when touched

---

## Testing Checklist (Manual)

When making changes, spot-check:

- [ ] Fresh launch with no `.minecraft` folder
- [ ] Global mode launch (vanilla + modded version)
- [ ] Instance mode: create, select, launch
- [ ] MS login device flow (needs network)
- [ ] Theme switch (especially Purple + Amber Glow)
- [ ] Modrinth search with Fabric/Forge version selected
- [ ] Loader install from New Instance dialog
- [ ] Portable mode toggle + restart
