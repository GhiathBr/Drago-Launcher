import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from theme_manager import THEMES, THEME_NAMES, DEFAULT_THEME, apply_theme


def test_themes_exist():
    assert len(THEMES) >= 5
    assert DEFAULT_THEME in THEMES


def test_theme_names():
    assert len(THEME_NAMES) == len(THEMES)
    for name in THEME_NAMES:
        assert name in THEMES


def test_theme_structure():
    for name, theme in THEMES.items():
        assert "appearance" in theme
        assert "color" in theme
        assert "sidebar_bg" in theme
        assert "card_bg" in theme
        assert "accent" in theme
        assert theme["appearance"] in ("dark", "light")


def test_default_theme():
    assert DEFAULT_THEME == "Drago Dark (Default)"
    theme = THEMES[DEFAULT_THEME]
    assert theme["appearance"] == "dark"
    assert theme["color"] == "blue"


if __name__ == "__main__":
    test_themes_exist()
    test_theme_names()
    test_theme_structure()
    test_default_theme()
    print("All theme_manager tests passed!")
