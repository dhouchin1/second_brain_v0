# Extension Icons

This folder should contain the extension icons in PNG format:

- `brain-16.png` - 16x16 pixel icon
- `brain-32.png` - 32x32 pixel icon  
- `brain-48.png` - 48x48 pixel icon
- `brain-128.png` - 128x128 pixel icon

## Creating Icons

You can create these icons from the provided `brain.svg` file using any SVG to PNG converter or image editor:

1. **Online converters**: Use tools like CloudConvert or SVG to PNG converters
2. **Command line**: Use ImageMagick: `convert brain.svg -resize 48x48 brain-48.png`
3. **Image editors**: Import the SVG into Figma, GIMP, or Photoshop and export as PNG

## Temporary Solution

For quick testing, you can:
1. Use any brain/head icon PNG files you have
2. Rename them to match the expected filenames above
3. Or comment out the "icons" section in manifest.json temporarily

## Icon Design

The brain icon should:
- Use the brand colors (purple/blue gradient: #667eea to #764ba2)
- Be simple and recognizable at small sizes
- Work well on both light and dark backgrounds
- Follow platform icon guidelines