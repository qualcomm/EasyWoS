#!/usr/bin/env python3
"""
Add Windows ARM64 support to Makefile.
"""

import os
import re
import sys
import shutil


def add_make_arm64(file_path, backup=True):
    """Add Windows ARM64 support to a Makefile."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        if backup:
            backup_path = f"{file_path}.bak"
            shutil.copy2(file_path, backup_path)
            print(f"Backup created: {backup_path}")
        
        # ARM64 support block for Makefile
        arm64_block = """
# Windows ARM64 support
ifeq ($(OS),Windows_NT)
    ifeq ($(PROCESSOR_ARCHITECTURE),ARM64)
        CFLAGS += -DWINDOWS_ARM64
        CXXFLAGS += -DWINDOWS_ARM64
        
        # Detect compiler
        ifeq ($(CC),cl)
            # MSVC compiler
            CFLAGS += /arch:armv8.0
            CXXFLAGS += /arch:armv8.0
        else
            # GCC/Clang compiler
            CFLAGS += -march=armv8-a
            CXXFLAGS += -march=armv8-a
        endif
    endif
endif
"""
        
        # Find best insertion point (after variable definitions, before rules)
        # Look for first rule (line starting with target:)
        lines = content.split('\n')
        insert_line = 0
        
        for i, line in enumerate(lines):
            # Skip comments and empty lines
            if line.strip().startswith('#') or not line.strip():
                continue
            # Found first rule
            if re.match(r'^[a-zA-Z0-9_\-\.]+\s*:', line):
                insert_line = i
                break
        
        if insert_line == 0:
            # No rules found, append at end
            modified_content = content + "\n" + arm64_block
        else:
            # Insert before first rule
            lines.insert(insert_line, arm64_block)
            modified_content = '\n'.join(lines)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(modified_content)
        
        print(f"✓ Modified: {file_path}")
        return True
    
    except Exception as e:
        print(f"✗ Error modifying {file_path}: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python enable_make_arm64.py <file_path> [--no-backup]")
        sys.exit(1)
    
    file_path = sys.argv[1]
    backup = "--no-backup" not in sys.argv
    
    if add_make_arm64(file_path, backup):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
