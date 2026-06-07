import customtkinter as ctk
import json
import os
import tempfile
import shutil
import zipfile


THEMES = {
    "Drago Dark (Default)": {
        "appearance": "dark",
        "color": "blue",
        "sidebar_bg": "#1e1e1e",
        "card_bg": "#2b2b2b",
        "accent": "#1f538d",
        "success": "#27ae60",
        "danger": "#c0392b",
        "warning": "#f39c12",
    },
    "Midnight Blue": {
        "appearance": "dark",
        "color": "dark-blue",
        "sidebar_bg": "#0d1b2a",
        "card_bg": "#1b2838",
        "accent": "#1b4965",
        "success": "#2d6a4f",
        "danger": "#9b2226",
        "warning": "#e09f3e",
    },
    "Deep Purple": {
        "appearance": "dark",
        "color": "purple",
        "sidebar_bg": "#1a0a2e",
        "card_bg": "#2d1b4e",
        "accent": "#5a189a",
        "success": "#52b788",
        "danger": "#c1121f",
        "warning": "#f4a261",
    },
    "Forest Green": {
        "appearance": "dark",
        "color": "green",
        "sidebar_bg": "#0a1c0a",
        "card_bg": "#1a3a1a",
        "accent": "#2d6a4f",
        "success": "#40916c",
        "danger": "#a4161a",
        "warning": "#e9c46a",
    },
    "Amber Glow": {
        "appearance": "dark",
        "color": "amber",
        "sidebar_bg": "#1c1500",
        "card_bg": "#2d2200",
        "accent": "#b8860b",
        "success": "#6b8e23",
        "danger": "#8b0000",
        "warning": "#ff8c00",
    },
    "Light Clean": {
        "appearance": "light",
        "color": "blue",
        "sidebar_bg": "#f0f0f0",
        "card_bg": "#ffffff",
        "accent": "#3a7ebf",
        "success": "#2ecc71",
        "danger": "#e74c3c",
        "warning": "#f39c12",
    },
    "High Contrast": {
        "appearance": "dark",
        "color": "blue",
        "sidebar_bg": "#000000",
        "card_bg": "#111111",
        "accent": "#00bfff",
        "success": "#00ff7f",
        "danger": "#ff4444",
        "warning": "#ffaa00",
    },
}

THEME_NAMES = list(THEMES.keys())
DEFAULT_THEME = "Drago Dark (Default)"

# Built-in color themes that CustomTkinter ships with
_BUILTIN_COLORS = {"blue", "dark-blue", "green"}

# Accent color overrides for non-built-in themes
_ACCENT_OVERRIDES = {
    "purple": {
        "primary": ["#9b59b6", "#7b2d8e"],
        "primary_hover": ["#8e44ad", "#5a189a"],
        "entry_border": ["#9b59b6", "#7b2d8e"],
        "slider_button": ["#9b59b6", "#7b2d8e"],
        "scrollbar_button": ["#9b59b6", "#7b2d8e"],
        "progress": ["#9b59b6", "#7b2d8e"],
        "checkbox_border": ["#9b59b6", "#7b2d8e"],
        "frame_border": ["#9b59b6", "#7b2d8e"],
        "tab_border": ["#9b59b6", "#7b2d8e"],
        "segmented_fg": ["#9b59b6", "#7b2d8e"],
        "switch_button": ["#9b59b6", "#7b2d8e"],
    },
    "amber": {
        "primary": ["#d4a017", "#b8860b"],
        "primary_hover": ["#b8860b", "#8b6508"],
        "entry_border": ["#d4a017", "#b8860b"],
        "slider_button": ["#d4a017", "#b8860b"],
        "scrollbar_button": ["#d4a017", "#b8860b"],
        "progress": ["#d4a017", "#b8860b"],
        "checkbox_border": ["#d4a017", "#b8860b"],
        "frame_border": ["#d4a017", "#b8860b"],
        "tab_border": ["#d4a017", "#b8860b"],
        "segmented_fg": ["#d4a017", "#b8860b"],
        "switch_button": ["#d4a017", "#b8860b"],
    },
}

_CUSTOM_THEMES_DIR = None


def _get_theme_dir():
    global _CUSTOM_THEMES_DIR
    if _CUSTOM_THEMES_DIR is None:
        _CUSTOM_THEMES_DIR = os.path.join(tempfile.gettempdir(), "drago_ctk_themes")
        os.makedirs(_CUSTOM_THEMES_DIR, exist_ok=True)
    return _CUSTOM_THEMES_DIR


def _extract_default_theme():
    """Extract the built-in blue theme JSON from CustomTkinter's package."""
    import customtkinter as ctk
    pkg_dir = os.path.dirname(ctk.__file__)
    theme_path = os.path.join(pkg_dir, "assets", "themes", "blue.json")
    alt_path = os.path.join(pkg_dir, "windows", "widgets", "theme", "blue.json")
    for path in [theme_path, alt_path]:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    return None


def _build_custom_theme(name):
    base = _extract_default_theme()
    if base is None:
        return None
    overrides = _ACCENT_OVERRIDES.get(name)
    if overrides is None:
        return base
    accented = json.loads(json.dumps(base))
    mapping = {
        "CTkButton": {"fg_color": "primary", "hover_color": "primary_hover"},
        "CTkEntry": {"border_color": "entry_border"},
        "CTkSlider": {"button_color": "slider_button"},
        "CTkScrollbar": {"button_color": "scrollbar_button"},
        "CTkProgressBar": {"fg_color": "progress"},
        "CTkCheckBox": {"border_color": "checkbox_border"},
        "CTkFrame": {"border_color": "frame_border"},
        "CTkTabview": {"border_color": "tab_border"},
        "CTkSegmentedButton": {"selected_fg_color": "segmented_fg"},
        "CTkSwitch": {"button_color": "switch_button"},
    }
    for widget_class, props in mapping.items():
        for prop_key, override_key in props.items():
            widget = accented.get(widget_class)
            if widget and override_key in overrides:
                if prop_key in widget:
                    widget[prop_key] = overrides[override_key]
    return accented


def apply_theme(theme_name: str):
    theme = THEMES.get(theme_name, THEMES[DEFAULT_THEME])
    ctk.set_appearance_mode(theme["appearance"])

    color = theme["color"]
    if color in _BUILTIN_COLORS:
        ctk.set_default_color_theme(color)
    else:
        theme_data = _build_custom_theme(color)
        theme_path = os.path.join(_get_theme_dir(), f"{color}.json")
        with open(theme_path, "w") as f:
            json.dump(theme_data, f, indent=4)
        ctk.set_default_color_theme(theme_path)

    return theme


def get_theme_names() -> list[str]:
    return THEME_NAMES
