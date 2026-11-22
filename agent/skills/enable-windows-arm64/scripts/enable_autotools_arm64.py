#!/usr/bin/env python3
"""
Add Windows ARM64 support to Autotools files (configure.ac, Makefile.am).
"""

import os
import re
import sys
import shutil


def _macro_call_line_end(content, name):
    """Return the end of the line where the first call of `name` ends.

    Only calls at the start of a line count, so comments and `dnl` lines are
    skipped. Variants such as AC_PROG_CC_C99 and the full argument list,
    including nested parentheses, are part of the call.
    """
    match = re.search(rf'^[ \t]*{name}\w*', content, re.MULTILINE)
    if not match:
        return None
    pos = match.end()
    if content.startswith('(', pos):
        depth = 0
        for i in range(pos, len(content)):
            if content[i] == '(':
                depth += 1
            elif content[i] == ')':
                depth -= 1
                if depth == 0:
                    pos = i + 1
                    break
    end = content.find('\n', pos)
    return len(content) if end == -1 else end


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
windows_arm64=no
case "$host" in
    aarch64-*-mingw* | arm64-*-mingw*)
        windows_arm64=yes
        AC_DEFINE([WINDOWS_ARM64], [1], [Define if building for Windows ARM64])
        CFLAGS="$CFLAGS -march=armv8-a"
        CXXFLAGS="$CXXFLAGS -march=armv8-a"
        ;;
esac
"""
        # The WINDOWS_ARM64 conditional used by Makefile.am needs automake
        if re.search(r'^[ \t]*AM_INIT_AUTOMAKE', content, re.MULTILINE):
            arm64_block += 'AM_CONDITIONAL([WINDOWS_ARM64], [test "x$windows_arm64" = xyes])\n'
        
        # Find insertion point after AC_INIT or AC_PROG_CC
        ac_init_end = _macro_call_line_end(content, 'AC_INIT')
        ac_prog_cc_end = _macro_call_line_end(content, 'AC_PROG_CC')
        
        if ac_prog_cc_end is not None:
            insert_pos = ac_prog_cc_end
        elif ac_init_end is not None:
            insert_pos = ac_init_end
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
        
        # automake only accepts '+=' on a variable that was already set with
        # '=', so start AM_CFLAGS/AM_CXXFLAGS with '=' when the file has none.
        def assign(var):
            if re.search(rf'^{var}\s*=', content, re.MULTILINE):
                return f"{var} +="
            return f"{var} ="

        # ARM64 support block for Makefile.am
        arm64_block = f"""
# Windows ARM64 support
if WINDOWS_ARM64
{assign('AM_CFLAGS')} -DWINDOWS_ARM64 -march=armv8-a
{assign('AM_CXXFLAGS')} -DWINDOWS_ARM64 -march=armv8-a
endif
"""
        
        # Append at the end, after any AM_CFLAGS/AM_CXXFLAGS definitions
        # (including ones continued over several lines)
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
