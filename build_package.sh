#!/bin/bash

# Mem0 Dify Plugin Package Builder
# This script creates a .difypkg file for the Mem0 plugin

set -e

PLUGIN_NAME="mem0ai"
VERSION="0.0.3"
OUTPUT_FILE="${PLUGIN_NAME}-${VERSION}.difypkg"
TEMP_DIR="temp_package"

echo "🚀 Building Mem0 Dify Plugin v${VERSION}..."

# Clean up previous builds
rm -rf "$TEMP_DIR" "$OUTPUT_FILE"
mkdir -p "$TEMP_DIR"

# Copy essential files
echo "📦 Copying plugin files..."

# Core files
cp manifest.yaml "$TEMP_DIR/"
cp main.py "$TEMP_DIR/"
cp requirements.txt "$TEMP_DIR/"
cp PRIVACY.md "$TEMP_DIR/"
cp README.md "$TEMP_DIR/"
cp CHANGELOG.md "$TEMP_DIR/"
cp .difyignore "$TEMP_DIR/"

# Copy provider directory
cp -r provider "$TEMP_DIR/"

# Copy tools directory
cp -r tools "$TEMP_DIR/"

# Copy assets directory
cp -r _assets "$TEMP_DIR/"

# Remove any Python cache files
echo "🧹 Cleaning up..."
find "$TEMP_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$TEMP_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true
find "$TEMP_DIR" -type f -name "*.pyo" -delete 2>/dev/null || true
find "$TEMP_DIR" -type f -name ".DS_Store" -delete 2>/dev/null || true

# Create the .difypkg file (it's just a zip file)
echo "📦 Creating ${OUTPUT_FILE}..."
cd "$TEMP_DIR"
# Use -D to not create directory entries in zip
zip -r -D "../${OUTPUT_FILE}" . -q
cd ..

# Clean up temp directory
rm -rf "$TEMP_DIR"

# Get file size
FILE_SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)

echo "✅ Package created successfully!"
echo ""
echo "📄 Package Details:"
echo "   Name: ${OUTPUT_FILE}"
echo "   Size: ${FILE_SIZE}"
echo "   Location: $(pwd)/${OUTPUT_FILE}"
echo ""
echo "🎉 You can now upload this package to Dify!"
