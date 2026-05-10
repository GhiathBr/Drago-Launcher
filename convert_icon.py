from PIL import Image

# Open the PNG image
img = Image.open('icon.png')

# Convert to RGBA if not already
img = img.convert('RGBA')

# Save as ICO with multiple sizes for better Windows compatibility
img.save('icon.ico', format='ICO', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

print("✓ Successfully converted icon.png to icon.ico")
