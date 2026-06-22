#!/usr/bin/env python3
"""
Add Windows ARM64 support to CMake files.
"""

import os
import sys
import json


def ensure_cmake_presets(project_dir):
    """Ensure CMakePresets.json exists with a windows-arm64 configuration."""
    presets_path = os.path.join(project_dir, "CMakePresets.json")
    
    arm64_preset = {
        "name": "windows-arm64",
        "displayName": "Windows ARM64",
        "description": "Target Windows on ARM64",
        "architecture": {
            "value": "ARM64",
            "strategy": "set"
        },
        "cacheVariables": {
            "CMAKE_BUILD_TYPE": "Release"
        }
    }

    try:
        content = {}
        if os.path.exists(presets_path):
            try:
                with open(presets_path, 'r', encoding='utf-8') as f:
                    content = json.load(f)
            except json.JSONDecodeError:
                print(f"⚠ Warning: {presets_path} exists but is invalid JSON. Creating new file.")

        # Ensure basic structure
        if "version" not in content:
            content["version"] = 3
        if "configurePresets" not in content:
            content["configurePresets"] = []

        # Check if windows-arm64 already exists
        exists = any(p.get("name") == "windows-arm64" for p in content["configurePresets"])
        
        if not exists:
            content["configurePresets"].append(arm64_preset)
            with open(presets_path, 'w', encoding='utf-8') as f:
                json.dump(content, f, indent=4)
            print(f"✓ Created/Updated: {presets_path} (added windows-arm64 preset)")
        else:
            print(f"  Preset 'windows-arm64' already exists in {presets_path}")
            
    except Exception as e:
        print(f"⚠ Failed to update CMakePresets.json: {e}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python enable_cmake_arm64.py <file_path>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    
    # Try to set up CMakePresets.json in the same directory
    project_dir = os.path.dirname(os.path.abspath(file_path))
    ensure_cmake_presets(project_dir)

    print("\\nTo build for Windows ARM64 using MSVC (or Clang-CL), run:")
    print("  cmake --preset windows-arm64")
    print("  -- OR --")
    print("  cmake -S . -B build_arm64 -A ARM64")
    print("  cmake --build build_arm64 --config Release")


if __name__ == "__main__":
    main()
