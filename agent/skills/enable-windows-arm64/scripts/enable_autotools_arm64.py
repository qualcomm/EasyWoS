#!/usr/bin/env python3
"""
Add Windows ARM64 support to Autotools files (configure.ac, Makefile.am).
"""

import os
import re
import sys
import shutil


def add_configure_ac_arm64(file_path, backup=True):
    """Add Windows ARM64 support to configure.ac."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        if backup:
            backup_path = f"{file_path}.bak"
            shutil.copy2(file_path, backup_path)
            print(f"Backup created: {backup_path}")
        
        # ARM64 support block for configure.ac
        arm64_block = """
# Windows ARM64 support
AC_CANONICAL_HOST
case "$host" in
    aarch64-*-mingw* | arm64-*-mingw*)
        AC_DEFINE([WINDOWS_ARM64], [1], [Define if building for Windows ARM64])
        CFLAGS="$CFLAGS -march=armv8-a"
        CXXFLAGS="$CXXFLAGS -march=armv8-a"
        ;;
esac
"""
        
        # Find insertion point after AC_INIT or AC_PROG_CC
        ac_init_match = re.search(r'AC_INIT\s*\([^)]*\)', content)
        ac_prog_cc_match = re.search(r'AC_PROG_CC', content)
        
        if ac_prog_cc_match:
            insert_pos = ac_prog_cc_match.end()
        elif ac_init_match:
            insert_pos = ac_init_match.end()
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


def add_makefile_am_arm64(file_path, backup=True):
    """Add Windows ARM64 support to Makefile.am."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        if backup:
            backup_path = f"{file_path}.bak"
            shutil.copy2(file_path, backup_path)
            print(f"Backup created: {backup_path}")
        
        # ARM64 support block for Makefile.am
        arm64_block = """
# Windows ARM64 support
if WINDOWS_ARM64
AM_CFLAGS += -DWINDOWS_ARM64 -march=armv8-a
AM_CXXFLAGS += -DWINDOWS_ARM64 -march=armv8-a
endif
"""
        
        # Append at the end or after AM_CFLAGS/AM_CXXFLAGS definitions
        am_flags_match = re.search(r'AM_C(XX)?FLAGS\s*[+]?=', content)
        
        if am_flags_match:
            # Find end of line
            line_end = content.find('\n', am_flags_match.end())
            if line_end != -1:
                insert_pos = line_end + 1
            else:
                insert_pos = len(content)
        else:
            insert_pos = len(content)
        
        modified_content = content[:insert_pos] + "\n" + arm64_block + "\n" + content[insert_pos:]
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(modified_content)
        
        print(f"[OK] Modified: {file_path}")
        return True
    
    except Exception as e:
        print(f"[ERROR] Error modifying {file_path}: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python enable_autotools_arm64.py <file_path> [--no-backup]")
        sys.exit(1)
    
    file_path = sys.argv[1]
    backup = "--no-backup" not in sys.argv
    
    if file_path.endswith('configure.ac') or file_path.endswith('configure.in'):
        success = add_configure_ac_arm64(file_path, backup)
    elif file_path.endswith('Makefile.am'):
        success = add_makefile_am_arm64(file_path, backup)
    else:
        print(f"Unsupported file type: {file_path}")
        sys.exit(1)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
