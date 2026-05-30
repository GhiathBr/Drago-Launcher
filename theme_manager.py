import customtkinter as ctk


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
        "color": "yellow",
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


def apply_theme(theme_name: str):
    theme = THEMES.get(theme_name, THEMES[DEFAULT_THEME])
    ctk.set_appearance_mode(theme["appearance"])
    ctk.set_default_color_theme(theme["color"])
    return theme


def get_theme_names() -> list[str]:
    return THEME_NAMES
