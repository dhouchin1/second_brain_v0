#!/usr/bin/env python3
"""
Apple Shortcuts Import Script for Second Brain
Converts JSON shortcut definitions to importable format for Mac Shortcuts app
"""

import json
import os
import base64
import plistlib
from pathlib import Path
from typing import Dict, Any, List
import argparse


class ShortcutConverter:
    """Convert JSON shortcut definitions to Apple Shortcuts format."""

    def __init__(self, server_url: str = "http://localhost:8082"):
        self.server_url = server_url
        self.output_dir = Path("./shortcuts_bundle")
        self.output_dir.mkdir(exist_ok=True)

    def convert_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a JSON action to Apple Shortcuts action format."""
        action_type = action.get("type", "comment")

        # Map of JSON action types to Shortcuts action identifiers
        action_map = {
            "comment": "is.workflow.actions.comment",
            "dictate_text": "is.workflow.actions.dictatetext",
            "get_current_location": "is.workflow.actions.getcurrentlocation",
            "get_current_date": "is.workflow.actions.date",
            "get_device_details": "is.workflow.actions.getdevicedetails",
            "build_dictionary": "is.workflow.actions.dictionary",
            "http_request": "is.workflow.actions.downloadurl",
            "show_notification": "is.workflow.actions.notification",
            "show_result": "is.workflow.actions.showresult",
            "take_photo": "is.workflow.actions.takephoto",
            "base64_encode": "is.workflow.actions.base64encode",
            "ask_for_input": "is.workflow.actions.ask",
            "choose_from_list": "is.workflow.actions.choosefromlist",
            "split_text": "is.workflow.actions.text.split",
            "get_urls_from_input": "is.workflow.actions.detect.link",
            "get_text_from_input": "is.workflow.actions.gettext",
            "if": "is.workflow.actions.conditional"
        }

        return {
            "WFWorkflowActionIdentifier": action_map.get(action_type, "is.workflow.actions.comment"),
            "WFWorkflowActionParameters": self._get_action_parameters(action)
        }

    def _get_action_parameters(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Extract parameters for an action."""
        params = {}
        action_type = action.get("type")

        if action_type == "comment":
            params["WFCommentActionText"] = action.get("text", "")

        elif action_type == "http_request":
            params["WFHTTPMethod"] = action.get("method", "POST")
            params["WFURL"] = action.get("url", "").replace("localhost:8082", self.server_url)
            params["WFHTTPHeaders"] = action.get("headers", {})
            params["WFHTTPBodyType"] = "Json"

        elif action_type == "show_notification":
            params["WFNotificationActionTitle"] = action.get("title", "")
            params["WFNotificationActionBody"] = action.get("body", "")

        elif action_type == "ask_for_input":
            params["WFInputPrompt"] = action.get("prompt", "")
            params["WFInputType"] = action.get("input_type", "Text")

        elif action_type == "choose_from_list":
            params["WFChooseFromListActionPrompt"] = action.get("prompt", "")
            params["WFChooseFromListActionItems"] = action.get("items", [])

        return params

    def create_shortcut_plist(self, shortcut_def: Dict[str, Any]) -> Dict[str, Any]:
        """Create a complete shortcut plist structure."""
        actions = [self.convert_action(action) for action in shortcut_def.get("actions", [])]

        return {
            "WFWorkflowActions": actions,
            "WFWorkflowClientRelease": "900",
            "WFWorkflowClientVersion": "900",
            "WFWorkflowIcon": {
                "WFWorkflowIconStartColor": self._get_color_value(shortcut_def.get("color", "blue")),
                "WFWorkflowIconGlyphNumber": 59511
            },
            "WFWorkflowImportQuestions": [],
            "WFWorkflowInputContentItemClasses": [
                "WFAppStoreAppContentItem",
                "WFArticleContentItem",
                "WFContactContentItem",
                "WFDateContentItem",
                "WFEmailAddressContentItem",
                "WFGenericFileContentItem",
                "WFImageContentItem",
                "WFLocationContentItem",
                "WFPDFContentItem",
                "WFPhoneNumberContentItem",
                "WFRichTextContentItem",
                "WFSafariWebPageContentItem",
                "WFStringContentItem",
                "WFURLContentItem"
            ],
            "WFWorkflowMinimumClientRelease": "900",
            "WFWorkflowMinimumClientVersion": "900",
            "WFWorkflowTypes": ["NCWidget", "WatchKit"]
        }

    def _get_color_value(self, color_name: str) -> int:
        """Convert color name to Shortcuts color value."""
        colors = {
            "blue": 4282601983,
            "purple": 4251333119,
            "teal": 431817727,
            "orange": 4271458815,
            "red": 4294902015,
            "indigo": 4284861575,
            "pink": 4292093695,
            "brown": 4274264319,
            "green": 4292093695,
            "yellow": 4294951175
        }
        return colors.get(color_name, 4282601983)

    def convert_shortcut(self, json_path: Path) -> None:
        """Convert a single JSON shortcut file."""
        with open(json_path, 'r') as f:
            shortcut_def = json.load(f)

        name = shortcut_def.get("name", json_path.stem)
        print(f"Converting: {name}")

        # Create plist structure
        plist_data = self.create_shortcut_plist(shortcut_def)

        # Save as plist file
        output_path = self.output_dir / f"{json_path.stem}.shortcut"
        with open(output_path, 'wb') as f:
            plistlib.dump(plist_data, f)

        print(f"  ✅ Created: {output_path}")

        # Also save metadata
        metadata_path = self.output_dir / f"{json_path.stem}_metadata.json"
        metadata = {
            "name": name,
            "description": shortcut_def.get("description", ""),
            "icon": shortcut_def.get("icon", ""),
            "siri_phrase": shortcut_def.get("siri_phrase", ""),
            "endpoint": shortcut_def.get("endpoint", ""),
            "sample_payload": shortcut_def.get("sample_payload", {}),
            "expected_response": shortcut_def.get("expected_response", {})
        }

        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        print(f"  📄 Metadata: {metadata_path}")

    def convert_all(self, shortcuts_dir: Path) -> None:
        """Convert all JSON shortcuts in a directory."""
        json_files = sorted(shortcuts_dir.glob("*.json"))
        json_files = [f for f in json_files if f.name != "sample_data.json"]

        if not json_files:
            print("⚠️  No shortcut JSON files found")
            return

        print(f"\n🔄 Converting {len(json_files)} shortcuts...")
        print(f"📁 Output directory: {self.output_dir}\n")

        for json_file in json_files:
            self.convert_shortcut(json_file)

        self._create_readme()
        self._create_import_script()

        print(f"\n✅ Conversion complete!")
        print(f"\n📦 Bundle ready at: {self.output_dir.absolute()}")
        print(f"\nNext steps:")
        print(f"1. Copy the shortcuts_bundle folder to your Mac")
        print(f"2. Double-click .shortcut files to import into Shortcuts app")
        print(f"3. Or run: ./shortcuts_bundle/import_all.sh")

    def _create_readme(self) -> None:
        """Create README for the bundle."""
        readme_content = """# Second Brain Apple Shortcuts Bundle

This bundle contains pre-configured Apple Shortcuts for seamless integration with your Second Brain.

## Contents

- **.shortcut files**: Ready to import into Apple Shortcuts app
- **_metadata.json files**: Documentation and sample data for each shortcut
- **import_all.sh**: Batch import script for Mac

## Installation (Mac)

### Method 1: Individual Import
1. Double-click any .shortcut file
2. The Shortcuts app will open
3. Click "Add Shortcut" to import
4. Repeat for each shortcut you want

### Method 2: Batch Import (Recommended)
```bash
chmod +x import_all.sh
./import_all.sh
```

## Installation (iPhone/iPad)

1. AirDrop the .shortcut files to your iOS device
2. Tap to open in Shortcuts app
3. Tap "Add Shortcut"
4. Configure server URL in each shortcut (Settings > Shortcuts > Advanced)

## Configuration

**IMPORTANT:** Update the server URL in each shortcut:

1. Open the shortcut in Shortcuts app
2. Find the "Get Contents of URL" action
3. Change `http://localhost:8082` to your server address
4. Save the shortcut

## Siri Integration

To use shortcuts with Siri:

1. Open each shortcut
2. Tap the settings icon (...)
3. Tap "Add to Siri"
4. Record your custom phrase

Suggested Siri phrases are in each shortcut's metadata file.

## Available Shortcuts

See individual *_metadata.json files for details on each shortcut including:
- Description and use cases
- Sample payloads
- Expected responses
- Siri phrase suggestions

## Troubleshooting

- **"Untrusted Shortcut" error**: Settings > Shortcuts > Advanced > Allow Untrusted Shortcuts
- **Authentication errors**: Log into Second Brain via Safari first
- **Network errors**: Ensure server URL is correct and accessible

## Support

For issues or questions, check the Second Brain documentation or open an issue on GitHub.
"""

        readme_path = self.output_dir / "README.md"
        with open(readme_path, 'w') as f:
            f.write(readme_content)

        print(f"  📝 Created: {readme_path}")

    def _create_import_script(self) -> None:
        """Create shell script for batch importing on Mac."""
        script_content = """#!/bin/bash

# Batch import script for Second Brain Apple Shortcuts
# macOS only - requires Shortcuts app

echo "📱 Second Brain Shortcuts Import"
echo "================================"
echo ""

SHORTCUT_FILES=(*.shortcut)

if [ ${#SHORTCUT_FILES[@]} -eq 0 ]; then
    echo "❌ No .shortcut files found"
    exit 1
fi

echo "Found ${#SHORTCUT_FILES[@]} shortcuts to import"
echo ""

for shortcut in "${SHORTCUT_FILES[@]}"; do
    echo "Importing: $shortcut"
    open "$shortcut"
    sleep 2  # Give Shortcuts app time to process
done

echo ""
echo "✅ Import process started"
echo ""
echo "⚠️  Note: You'll need to click 'Add Shortcut' for each one in the Shortcuts app"
echo "⚠️  Don't forget to update the server URL in each shortcut!"
"""

        script_path = self.output_dir / "import_all.sh"
        with open(script_path, 'w') as f:
            f.write(script_content)

        # Make executable
        os.chmod(script_path, 0o755)

        print(f"  🔧 Created: {script_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert Second Brain shortcut JSON definitions to importable Apple Shortcuts"
    )
    parser.add_argument(
        "--server-url",
        default="http://localhost:8082",
        help="Your Second Brain server URL (default: http://localhost:8082)"
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("."),
        help="Directory containing JSON shortcut definitions"
    )

    args = parser.parse_args()

    print("🧠 Second Brain - Apple Shortcuts Converter")
    print("=" * 50)
    print(f"Server URL: {args.server_url}")
    print(f"Input directory: {args.input_dir}")

    converter = ShortcutConverter(server_url=args.server_url)
    converter.convert_all(args.input_dir)


if __name__ == "__main__":
    main()
