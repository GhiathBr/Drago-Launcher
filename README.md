# 🐉 Drago Launcher

A highly customized, safe, and feature-rich Minecraft Launcher built with Python and CustomTkinter. Drago Launcher is designed to provide a clean, modern user interface while packing powerful Quality of Life (QoL) features like **full instance isolation**, built-in mod management, world management, and custom skin support.

## ✨ Key Features

### 🎯 **Instance System** (NEW!)
The most powerful feature - complete game isolation for maximum flexibility:

- **Create Unlimited Instances:** Each with its own mods, saves, configs, and settings
- **Full Isolation:** Every instance has separate:
  - Mods folder
  - Saves/worlds
  - Resource packs
  - Shader packs
  - Config files
  - Logs & screenshots
  - Crash reports
- **Per-Instance Settings:**
  - Custom RAM allocation (min/max)
  - Custom Java path
  - Window resolution
  - Fullscreen mode
  - Custom JVM arguments
- **Instance Management:**
  - Duplicate instances instantly
  - Import/Export instances as packages
  - Rename instances
  - Mark favorites (⭐)
  - Track play statistics (play count, total playtime)
  - Recently played tracking
- **Smart Organization:** Favorites appear first, sorted by last played

**Example Use Cases:**
```
instances/
  ├── Vanilla 1.20.1/          # Pure vanilla gameplay
  ├── Fabric Survival/         # Modded survival with optimization mods
  ├── Forge Tech Pack/         # Heavy tech modpack with 200+ mods
  ├── Skyblock Challenge/      # Skyblock with specific mod setup
  └── Creative Building/       # Creative mode with building mods
```

### 🎮 Built-in Modrinth Integration
- **Browse & Search:** Search the massive Modrinth database directly from the launcher
- **Detailed Mod Pages:** View full project descriptions, authors, and icons before downloading
- **1-Click Install:** Automatically downloads mods to your **current instance's** mods folder
- **Instance-Aware:** Mods install to the selected instance, keeping everything organized

### 👕 Custom Skins Manager
- **Visual Skin Preview:** Upload any standard `.png` skin and see a live face preview in the launcher.
- **CustomSkinLoader Support:** Automatically configures your game to apply the local skin to all clients and servers.

### 📁 Local Content Manager
- **Manage Mods:** View all currently installed mods in your current instance and delete unwanted ones
- **Manage Worlds:** Easily view and delete old single-player world saves
- **Instance-Specific:** Shows content only for the currently selected instance

### 🚀 Optimized Launching
- **Smart RAM Allocation:** Per-instance RAM settings with automatic system detection
- **Optimized JVM Arguments:** Modern Java Garbage Collection arguments pre-configured
- **Version Management:** Downloads and installs missing game versions seamlessly
- **Instance Isolation:** Each instance launches with its own isolated game directory

### 📰 Official News Feed
- Stays up to date by actively fetching the official Minecraft/Mojang news API directly to your home screen.

## 🛠️ Download & Usage

### 📥 The Executable (Recommended)
1. Go to the **Releases** tab on the right side of this GitHub repository.
2. Download the latest `DragoLauncher.exe`.
3. Run the executable. *(Note: Windows SmartScreen may show a blue warning since this is a new independently-published tool. Click "More Info" -> "Run anyway")*.

### 💻 Running from Source
If you are a developer and want to run or modify the Python code directly:

1. Clone the repository:
   ```bash
   git clone https://github.com/GhiathBr/Drago-Launcher.git
   ```
2. Install the required dependencies:
   ```bash
   pip install customtkinter minecraft-launcher-lib requests Pillow
   ```
3. Run the launcher:
   ```bash
   python luncher.py
   ```

## 🏗️ Technologies Used
- **Python 3**
- **CustomTkinter:** For the sleek, dark-mode graphical user interface.
- **minecraft-launcher-lib:** For validating, downloading, and launching the core game files.
- **Requests & Pillow:** For multi-threaded API calls and in-memory image processing.
- **PyInstaller:** For compiling the standalone Windows executable.