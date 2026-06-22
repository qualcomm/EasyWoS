#!/usr/bin/env python3
"""
Add Windows ARM64 support to remaining build systems (Ninja, QMake, SCons).
"""

import os
import re
import sys
import shutil


def add_ninja_arm64(file_path, backup=True):
    """Add Windows ARM64 support to build.ninja."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        if backup:
            backup_path = f"{file_path}.bak"
            shutil.copy2(file_path, backup_path)
            print(f"Backup created: {backup_path}")
        
        # ARM64 support for Ninja
        arm64_block = """
# Windows ARM64 support
arm64_cflags = -DWINDOWS_ARM64 -march=armv8-a
arm64_cxxflags = -DWINDOWS_ARM64 -march=armv8-a

rule cc_arm64
  command = $cc $arm64_cflags $cflags -c $in -o $out
  description = CC $out

rule cxx_arm64
  command = $cxx $arm64_cxxflags $cxxflags -c $in -o $out
  description = CXX $out
"""
        
        # Insert at the beginning
        modified_content = arm64_block + "\n" + content
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(modified_content)
        
        print(f"✓ Modified: {file_path}")
        return True
    
    except Exception as e:
        print(f"✗ Error modifying {file_path}: {e}")
        return False


def add_qmake_arm64(file_path, backup=True):
    """Add Windows ARM64 support to .pro file."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        if backup:
            backup_path = f"{file_path}.bak"
            shutil.copy2(file_path, backup_path)
            print(f"Backup created: {backup_path}")
        
        # ARM64 support for QMake
        arm64_block = """
# Windows ARM64 support
win32 {
    contains(QMAKE_TARGET.arch, arm64) {
        DEFINES += WINDOWS_ARM64
        QMAKE_CFLAGS += -march=armv8-a
        QMAKE_CXXFLAGS += -march=armv8-a
    }
}
"""
        
        # Append at the end
        modified_content = content + "\n" + arm64_block
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(modified_content)
        
        print(f"✓ Modified: {file_path}")
        return True
    
    except Exception as e:
        print(f"✗ Error modifying {file_path}: {e}")
        return False


def add_scons_arm64(file_path, backup=True):
    """Add Windows ARM64 support to SConstruct/SConscript."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        if backup:
            backup_path = f"{file_path}.bak"
            shutil.copy2(file_path, backup_path)
            print(f"Backup created: {backup_path}")
        
        # ARM64 support for SCons
        arm64_block = """
# Windows ARM64 support
import platform
if platform.system() == 'Windows' and platform.machine() == 'ARM64':
    env.Append(CPPDEFINES=['WINDOWS_ARM64'])
    env.Append(CCFLAGS=['-march=armv8-a'])
    env.Append(CXXFLAGS=['-march=armv8-a'])
"""
        
        # Find Environment creation
        env_match = re.search(r'env\s*=\s*Environment\s*\(', content)
        
        if env_match:
            # Find end of Environment() call
            paren_count = 0
            pos = env_match.start()
            while pos < len(content):
                if content[pos] == '(':
                    paren_count += 1
                elif content[pos] == ')':
                    paren_count -= 1
                    if paren_count == 0:
                        insert_pos = pos + 1
                        # Skip to next line
                        while insert_pos < len(content) and content[insert_pos] != '\n':
                            insert_pos += 1
                        insert_pos += 1
                        break
                pos += 1
            else:
                insert_pos = env_match.end()
        else:
            # Append at end
            insert_pos = len(content)
        
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
        print("Usage: python enable_other_arm64.py <file_path> [--no-backup]")
        sys.exit(1)
    
    file_path = sys.argv[1]
    backup = "--no-backup" not in sys.argv
    
    if file_path.endswith('build.ninja') or file_path.endswith('.ninja'):
        success = add_ninja_arm64(file_path, backup)
    elif file_path.endswith('.pro') or file_path.endswith('.pri'):
        success = add_qmake_arm64(file_path, backup)
    elif file_path.endswith('SConstruct') or file_path.endswith('SConscript'):
        success = add_scons_arm64(file_path, backup)
    else:
        print(f"Unsupported file type: {file_path}")
        sys.exit(1)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
