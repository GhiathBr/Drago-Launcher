#!/usr/bin/env python3
"""Script to replace the skins tab with vertical layout"""

with open('luncher.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the skins tab section
start_marker = "# === SKINS TAB (with Mineskin.eu) ==="
end_marker = "# === MODRINTH MODS TAB ==="

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print("ERROR: Could not find skins tab markers")
    exit(1)

# Read the replacement
with open('skins_tab_vertical.txt', 'r', encoding='utf-8') as f:
    replacement = f.read()

# Replace
new_content = content[:start_idx] + replacement + "\n        " + content[end_idx:]

# Write back
with open('luncher.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("✓ Successfully replaced skins tab with vertical layout")
