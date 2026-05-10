# 🐉 Drago Launcher

A highly customized, safe, and feature-rich Minecraft Launcher built with Python and CustomTkinter. Drago Launcher is designed to provide a clean, modern user interface while packing powerful Quality of Life (QoL) features like built-in mod management, world management, and custom skin support.

## ✨ Key Features

### 🎮 Built-in Modrinth Integration
- **Browse & Search:** Search the massive Modrinth database directly from the launcher.
- **Detailed Mod Pages:** View full project descriptions, authors, and icons before downloading.
- **1-Click Install:** Automatically downloads the correct `.jar` file for your selected Minecraft version right into your `mods` folder.

### 👕 Custom Skins Manager
- **Visual Skin Preview:** Upload any standard `.png` skin and see a live face preview in the launcher.
- **CustomSkinLoader Support:** Automatically configures your game to apply the local skin to all clients and servers.

### 📁 Local Content Manager
- **Manage Mods:** View all currently installed mods in your `.minecraft/mods` directory and delete broken or unwanted ones with a single tap.
- **Manage Worlds:** Easily view and wipe old single-player world saves to free up disk space.

### 🚀 Optimized Launching
- **Smart RAM Allocation:** Automatically detects your PC's max physical memory and provides a safe slider to allocate RAM.
- **Optimized JVM Arguments:** Ships with modern Java Garbage Collection arguments pre-configured for maximum FPS and stability.
- **Version Management:** Downloads and installs missing game versions seamlessly with a built-in progress bar.

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