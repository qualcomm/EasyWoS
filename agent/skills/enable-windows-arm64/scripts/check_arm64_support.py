#!/usr/bin/env python3
"""
Check if a project already has Windows ARM64 support.
"""

import os
import re
import sys


def check_cmake_arm64(file_path):
    """Check if CMake file has ARM64 support."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Look for ARM64 or aarch64 references in meaningful contexts
        patterns = [
            r'CMAKE_SYSTEM_PROCESSOR.*ARM64',
            r'CMAKE_SYSTEM_PROCESSOR.*aarch64',
            r'PROCESSOR_ARCHITECTURE.*ARM64',
            r'set\s*\(\s*CMAKE_GENERATOR_PLATFORM\s+ARM64',
            r'if\s*\(\s*ARM64\s*\)',
            r'add_compile_options.*arm64',
            r'target_compile_options.*arm64',
        ]
        
        for pattern in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True
        
        return False
    except Exception as e:
        print(f"Error checking {file_path}: {e}")
        return False


def check_visual_studio_arm64(file_path):
    """Check if Visual Studio project has ARM64 configuration."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Check for ARM64 platform configuration
        patterns = [
            r'<Platform>ARM64</Platform>',
            r"'ARM64'\|",
            r'Include="[^"]*\|ARM64"',
            r'Condition=".*ARM64.*"',
        ]
        
        for pattern in patterns:
            if re.search(pattern, content):
                return True
        
        return False
    except Exception as e:
        print(f"Error checking {file_path}: {e}")
        return False


def check_make_arm64(file_path):
    """Check if Makefile has ARM64 support."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        patterns = [
            r'PROCESSOR_ARCHITECTURE.*ARM64',
            r'ifeq.*ARM64',
            r'ARCH\s*:?=\s*arm64',
            r'ARCH\s*:?=\s*aarch64',
            r'-march=armv8',
            r'/arch:arm64',
        ]
        
        for pattern in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True
        
        return False
    except Exception as e:
        print(f"Error checking {file_path}: {e}")
        return False


def check_autotools_arm64(file_path):
    """Check if Autotools file has ARM64 support."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        patterns = [
            r'aarch64.*mingw',
            r'arm64.*mingw',
            r'case.*aarch64',
            r'case.*arm64',
            r'host.*aarch64',
        ]
        
        for pattern in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True
        
        return False
    except Exception as e:
        print(f"Error checking {file_path}: {e}")
        return False


def check_bazel_arm64(file_path):
    """Check if Bazel file has ARM64 support."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        patterns = [
            r'cpu.*arm64',
            r'cpu.*aarch64',
            r'constraint_values.*arm64',
            r'@platforms//cpu:arm64',
            r'@platforms//cpu:aarch64',
        ]
        
        for pattern in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True
        
        return False
    except Exception as e:
        print(f"Error checking {file_path}: {e}")
        return False


def check_ninja_arm64(file_path):
    """Check if Ninja file has ARM64 support."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        patterns = [
            r'arm64',
            r'aarch64',
            r'-march=armv8',
            r'/arch:arm64',
        ]
        
        for pattern in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True
        
        return False
    except Exception as e:
        print(f"Error checking {file_path}: {e}")
        return False


def check_qmake_arm64(file_path):
    """Check if QMake file has ARM64 support."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        patterns = [
            r'contains.*ARM64',
            r'contains.*aarch64',
            r'QMAKE_TARGET\.arch.*arm64',
            r'win32-arm64',
        ]
        
        for pattern in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True
        
        return False
    except Exception as e:
        print(f"Error checking {file_path}: {e}")
        return False


def check_scons_arm64(file_path):
    """Check if SCons file has ARM64 support."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        patterns = [
            r'TARGET_ARCH.*arm64',
            r'TARGET_ARCH.*aarch64',
            r'platform.*arm64',
            r'-march=armv8',
            r'/arch:arm64',
        ]
        
        for pattern in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True
        
        return False
    except Exception as e:
        print(f"Error checking {file_path}: {e}")
        return False


# Checker function mapping
CHECKERS = {
    "cmake": check_cmake_arm64,
    "visual_studio": check_visual_studio_arm64,
    "make": check_make_arm64,
    "autotools": check_autotools_arm64,
    "bazel": check_bazel_arm64,
    "ninja": check_ninja_arm64,
    "qmake": check_qmake_arm64,
    "scons": check_scons_arm64,
}


def check_arm64_support(build_system, file_paths):
    """
    Check if any of the build files have ARM64 support.
    Returns: (has_support: bool, details: list)
    """
    checker = CHECKERS.get(build_system)
    if not checker:
        return False, [f"No checker available for {build_system}"]
    
    results = []
    has_support = False
    
    for file_path in file_paths:
        if checker(file_path):
            has_support = True
            results.append(f"✓ {file_path}: ARM64 support detected")
        else:
            results.append(f"✗ {file_path}: No ARM64 support")
    
    return has_support, results


def main():
    if len(sys.argv) < 3:
        print("Usage: python check_arm64_support.py <build_system> <file1> [file2] ...")
        sys.exit(1)
    
    build_system = sys.argv[1]
    file_paths = sys.argv[2:]
    
    has_support, details = check_arm64_support(build_system, file_paths)
    
    for detail in details:
        print(detail)
    
    if has_support:
        print("\nResult: Windows ARM64 support is already enabled")
        sys.exit(0)
    else:
        print("\nResult: Windows ARM64 support is NOT enabled")
        sys.exit(1)


if __name__ == "__main__":
    main()
