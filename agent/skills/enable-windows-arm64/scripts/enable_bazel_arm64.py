#!/usr/bin/env python3
"""
Add Windows ARM64 support to Bazel BUILD files.
"""

import os
import re
import sys
import shutil


def add_bazel_arm64(file_path, backup=True):
    """Add Windows ARM64 support to a Bazel BUILD file."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        if backup:
            backup_path = f"{file_path}.bak"
            shutil.copy2(file_path, backup_path)
            print(f"Backup created: {backup_path}")
        
        # ARM64 support block for Bazel
        arm64_block = """
# Windows ARM64 support
config_setting(
    name = "windows_arm64",
    constraint_values = [
        "@platforms//os:windows",
        "@platforms//cpu:aarch64",
    ],
)

# ARM64-specific compiler flags
cc_library(
    name = "arm64_flags",
    copts = select({
        ":windows_arm64": [
            "-DWINDOWS_ARM64",
            "-march=armv8-a",
        ],
        "//conditions:default": [],
    }),
)
"""
        
        # Find best insertion point (at the beginning after load statements)
        load_matches = list(re.finditer(r'^load\s*\(', content, re.MULTILINE))
        
        if load_matches:
            # Insert after last load statement
            last_load = load_matches[-1]
            # Find end of load statement (closing parenthesis)
            paren_count = 0
            pos = last_load.start()
            while pos < len(content):
                if content[pos] == '(':
                    paren_count += 1
                elif content[pos] == ')':
                    paren_count -= 1
                    if paren_count == 0:
                        insert_pos = pos + 1
                        break
                pos += 1
            else:
                insert_pos = last_load.end()
        else:
            insert_pos = 0
        
        modified_content = content[:insert_pos] + "\n" + arm64_block + "\n" + content[insert_pos:]
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(modified_content)
        
        print(f"✓ Modified: {file_path}")
        return True
    
    except Exception as e:
        print(f"✗ Error modifying {file_path}: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python enable_bazel_arm64.py <file_path> [--no-backup]")
        sys.exit(1)
    
    file_path = sys.argv[1]
    backup = "--no-backup" not in sys.argv
    
    if add_bazel_arm64(file_path, backup):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
