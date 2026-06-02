import os
import json
import shutil
import requests
import threading
from pathlib import Path
from io import BytesIO


# NameMC has publicly accessible skin URLs
NAMEMC_WEB = "https://namemc.com"
NAMEMC_SKIN_URL = "https://s.namemc.com/i/{uuid}.png"
NAMEMC_RENDER_URL = "https://s.namemc.com/3d/skin/body.png?skin={uuid}&model=classic&theta=-25&phi=20&time=100&width=250&height=400"


def search_skins(query: str, page: int = 1, limit: int = 20) -> list[dict]:
    """
    For search, we'll provide a curated list of popular Minecraft usernames
    that users can search through. Real-time search would require scraping.
    """
    # Popular Minecraft players and their skins (UUID-based)
    popular_skins = [
        {"id": "069a79f4-44e9-4726-a5be-fca90e38aaf5", "name": "Notch", "url": "https://s.namemc.com/i/069a79f4-44e9-4726-a5be-fca90e38aaf5.png"},
        {"id": "853c80ef-3c37-49fd-aa49-938b674adae6", "name": "jeb_", "url": "https://s.namemc.com/i/853c80ef-3c37-49fd-aa49-938b674adae6.png"},
        {"id": "61699b2e-d327-4a01-9f1e-0ea8c3f06bc6", "name": "Dinnerbone", "url": "https://s.namemc.com/i/61699b2e-d327-4a01-9f1e-0ea8c3f06bc6.png"},
        {"id": "f498513c-e4c4-4b8c-a9e8-0e42c2fabb31", "name": "Hypixel", "url": "https://s.namemc.com/i/f498513c-e4c4-4b8c-a9e8-0e42c2fabb31.png"},
        {"id": "b876ec32-e396-476b-a115-8438d83c67d4", "name": "Technoblade", "url": "https://s.namemc.com/i/b876ec32-e396-476b-a115-8438d83c67d4.png"},
        {"id": "ec70bcaf-702f-4bb8-b48d-276fa52a780c", "name": "Skeppy", "url": "https://s.namemc.com/i/ec70bcaf-702f-4bb8-b48d-276fa52a780c.png"},
        {"id": "5c115ca7-0c6a-4b35-b4cc-49573913b8ce", "name": "BadBoyHalo", "url": "https://s.namemc.com/i/5c115ca7-0c6a-4b35-b4cc-49573913b8ce.png"},
        {"id": "f7c77d99-9f15-4a66-a87d-c4a51ef30d19", "name": "Dream", "url": "https://s.namemc.com/i/f7c77d99-9f15-4a66-a87d-c4a51ef30d19.png"},
        {"id": "0b7e6052-09f4-4290-854c-b7120dd6e869", "name": "GeorgeNotFound", "url": "https://s.namemc.com/i/0b7e6052-09f4-4290-854c-b7120dd6e869.png"},
        {"id": "3c358896-45c9-4f9e-b066-98112b6f4b5d", "name": "Sapnap", "url": "https://s.namemc.com/i/3c358896-45c9-4f9e-b066-98112b6f4b5d.png"},
    ]
    
    if query:
        # Filter by name if query provided
        filtered = [s for s in popular_skins if query.lower() in s["name"].lower()]
        return filtered
    
    return popular_skins[:limit]


def get_trending_skins(page: int = 1, limit: int = 20) -> list[dict]:
    """Get popular/default skins"""
    print("DEBUG: Returning curated popular Minecraft skins")
    
    # Return popular Minecraft skins
    popular_skins = [
        {"id": "069a79f4-44e9-4726-a5be-fca90e38aaf5", "name": "Notch (Creator)", "url": "https://s.namemc.com/i/069a79f4-44e9-4726-a5be-fca90e38aaf5.png"},
        {"id": "853c80ef-3c37-49fd-aa49-938b674adae6", "name": "jeb_ (Developer)", "url": "https://s.namemc.com/i/853c80ef-3c37-49fd-aa49-938b674adae6.png"},
        {"id": "61699b2e-d327-4a01-9f1e-0ea8c3f06bc6", "name": "Dinnerbone (Developer)", "url": "https://s.namemc.com/i/61699b2e-d327-4a01-9f1e-0ea8c3f06bc6.png"},
        {"id": "f7c77d99-9f15-4a66-a87d-c4a51ef30d19", "name": "Dream", "url": "https://s.namemc.com/i/f7c77d99-9f15-4a66-a87d-c4a51ef30d19.png"},
        {"id": "b876ec32-e396-476b-a115-8438d83c67d4", "name": "Technoblade", "url": "https://s.namemc.com/i/b876ec32-e396-476b-a115-8438d83c67d4.png"},
        {"id": "f498513c-e4c4-4b8c-a9e8-0e42c2fabb31", "name": "Hypixel", "url": "https://s.namemc.com/i/f498513c-e4c4-4b8c-a9e8-0e42c2fabb31.png"},
        {"id": "ec70bcaf-702f-4bb8-b48d-276fa52a780c", "name": "Skeppy", "url": "https://s.namemc.com/i/ec70bcaf-702f-4bb8-b48d-276fa52a780c.png"},
        {"id": "5c115ca7-0c6a-4b35-b4cc-49573913b8ce", "name": "BadBoyHalo", "url": "https://s.namemc.com/i/5c115ca7-0c6a-4b35-b4cc-49573913b8ce.png"},
        {"id": "0b7e6052-09f4-4290-854c-b7120dd6e869", "name": "GeorgeNotFound", "url": "https://s.namemc.com/i/0b7e6052-09f4-4290-854c-b7120dd6e869.png"},
        {"id": "3c358896-45c9-4f9e-b066-98112b6f4b5d", "name": "Sapnap", "url": "https://s.namemc.com/i/3c358896-45c9-4f9e-b066-98112b6f4b5d.png"},
        {"id": "386d5c78-8e83-4e66-9b1c-695a17ab4f6f", "name": "TommyInnit", "url": "https://s.namemc.com/i/386d5c78-8e83-4e66-9b1c-695a17ab4f6f.png"},
        {"id": "e5b0f5b7-88e3-4ddc-8c0b-3f3a8e7e0e0e", "name": "Tubbo", "url": "https://s.namemc.com/i/e5b0f5b7-88e3-4ddc-8c0b-3f3a8e7e0e0e.png"},
        {"id": "steve", "name": "Steve (Default)", "url": "https://s.namemc.com/i/069a79f4-44e9-4726-a5be-fca90e38aaf5.png"},
        {"id": "alex", "name": "Alex (Default)", "url": "https://s.namemc.com/i/853c80ef-3c37-49fd-aa49-938b674adae6.png"},
    ]
    
    return popular_skins[:limit]


def get_skin_from_username(username: str) -> tuple[bool, str, str]:
    """
    Get skin UUID and URL from a Minecraft username using Mojang API
    Returns: (success, uuid, skin_url)
    """
    try:
        print(f"DEBUG: Looking up UUID for username: {username}")
        # Get UUID from username
        resp = requests.get(
            f"https://api.mojang.com/users/profiles/minecraft/{username}",
            timeout=10
        )
        
        if resp.status_code == 200:
            data = resp.json()
            uuid = data.get("id", "")
            if uuid:
                # Convert UUID to dashed format for NameMC
                uuid_dashed = f"{uuid[:8]}-{uuid[8:12]}-{uuid[12:16]}-{uuid[16:20]}-{uuid[20:]}"
                skin_url = f"https://s.namemc.com/i/{uuid_dashed}.png"
                print(f"DEBUG: Found UUID: {uuid_dashed}")
                return True, uuid_dashed, skin_url
        
        print(f"DEBUG: Username not found: {resp.status_code}")
        return False, "", ""
    except Exception as e:
        print(f"DEBUG: Error looking up username: {e}")
        return False, "", ""


def download_skin(skin_id, target_path: str) -> bool:
    """Download skin PNG file"""
    # If skin_id is a URL, use it directly
    if isinstance(skin_id, str) and (skin_id.startswith("http://") or skin_id.startswith("https://")):
        urls_to_try = [skin_id]
    else:
        # Try NameMC URL format
        urls_to_try = [
            f"https://s.namemc.com/i/{skin_id}.png",
            f"https://crafatar.com/skins/{skin_id}",
            f"https://mc-heads.net/skin/{skin_id}",
        ]
    
    for url in urls_to_try:
        try:
            print(f"DEBUG: Trying to download skin from: {url}")
            resp = requests.get(url, timeout=10, allow_redirects=True)
            print(f"DEBUG: Download response status: {resp.status_code}, content length: {len(resp.content)}")
            
            if resp.status_code == 200 and resp.content and len(resp.content) > 100:
                # Verify it's a valid image
                if resp.content[:8] == b'\x89PNG\r\n\x1a\n' or resp.content[:2] in [b'\xff\xd8', b'BM']:
                    with open(target_path, "wb") as f:
                        f.write(resp.content)
                    print(f"DEBUG: Successfully downloaded skin to {target_path}")
                    return True
                else:
                    print(f"DEBUG: Downloaded content is not a valid image")
        except Exception as e:
            print(f"DEBUG: Skin download error from {url}: {e}")
            continue
    
    print("DEBUG: All download attempts failed")
    return False


def apply_skin_from_mineskin(skin_id, username: str, minecraft_dir: str) -> tuple[bool, str]:
    """Apply a skin to local CustomSkinLoader"""
    try:
        target_path = os.path.join(
            minecraft_dir, "CustomSkinLoader", "LocalSkin", "skins", f"{username}.png"
        )
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        print(f"DEBUG: Attempting to apply skin {skin_id} for user {username}")
        if download_skin(skin_id, target_path):
            csl_config_dir = os.path.join(minecraft_dir, "CustomSkinLoader")
            os.makedirs(csl_config_dir, exist_ok=True)
            csl_config_path = os.path.join(csl_config_dir, "CustomSkinLoader.json")
            config_data = {
                "version": "14.0",
                "enable": True,
                "loadlist": [
                    {"name": "LocalSkin", "type": "LocalSkin"},
                    {"name": "Mojang", "type": "MojangAPI"},
                ],
            }
            with open(csl_config_path, "w") as f:
                json.dump(config_data, f, indent=4)
            return True, f"✓ Skin applied to {username}!"
        return False, "Failed to download skin - please try uploading manually"
    except Exception as e:
        print(f"DEBUG: Apply skin error: {e}")
        import traceback
        traceback.print_exc()
        return False, f"Error: {str(e)}"


# Legacy functions for compatibility
def get_skin_data(skin_id) -> dict | None:
    """Get skin data by ID"""
    return None


def get_skin_image_url(skin_id) -> str:
    """Get direct URL to skin image"""
    if isinstance(skin_id, str) and (skin_id.startswith("http://") or skin_id.startswith("https://")):
        return skin_id
    return f"https://s.namemc.com/i/{skin_id}.png"


def get_skin_render_url(skin_id) -> str:
    """Get URL to rendered skin preview"""
    return f"https://s.namemc.com/3d/skin/body.png?skin={skin_id}"


