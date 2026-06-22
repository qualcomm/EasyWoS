#!/usr/bin/env python3
"""
Detect build system in a project with priority ordering.
Priority: cmake > visual_studio > make > ninja > autotools > bazel > qmake > scons
"""

import os
import re
import sys
from pathlib import Path

# Build system detection with priority order
BUILD_SYSTEMS = [
    {
        "name": "cmake",
        "priority": 1,
        "files": ["CMakeLists.txt"],
        "patterns": [r"CMakeLists\.txt$"],
        "keywords": [r'cmake_minimum_required', r'project\s*\(']
    },
    {
        "name": "visual_studio",
        "priority": 2,
        "files": [".vcxproj", ".sln"],
        "patterns": [r"\.vcxproj$", r"\.sln$"],
        "keywords": [r'<Project', r'<PropertyGroup']
    },
    {
        "name": "make",
        "priority": 3,
        "files": ["Makefile", "makefile", "GNUmakefile"],
        "patterns": [r"[Mm]akefile$", r"GNUmakefile$"],
        "keywords": [r'^[A-Za-z0-9_\-]+\s*:', r'^\t']
    },
    {
        "name": "ninja",
        "priority": 4,
        "files": ["build.ninja"],
        "patterns": [r"build\.ninja$"],
        "keywords": [r'^rule\s+', r'^build\s+']
    },
    {
        "name": "autotools",
        "priority": 5,
        "files": ["configure.ac", "configure.in", "Makefile.am"],
        "patterns": [r"configure\.ac$", r"configure\.in$", r"Makefile\.am$"],
        "keywords": [r'AC_INIT', r'AM_INIT_AUTOMAKE']
    },
    {
        "name": "bazel",
        "priority": 6,
        "files": ["BUILD", "BUILD.bazel", "WORKSPACE"],
        "patterns": [r"BUILD$", r"BUILD\.bazel$", r"WORKSPACE$"],
        "keywords": [r'cc_library', r'cc_binary']
    },
    {
        "name": "qmake",
        "priority": 7,
        "files": [".pro"],
        "patterns": [r"\.pro$"],
        "keywords": [r'TEMPLATE\s*=', r'SOURCES\s*\+=']
    },
    {
        "name": "scons",
        "priority": 8,
        "files": ["SConstruct", "SConscript"],
        "patterns": [r"SConstruct$", r"SConscript$"],
        "keywords": [r'Environment\(', r'Program\(']
    }
]


def check_file_content(file_path, keywords):
    """Check if file content contains build system keywords."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read(8192)  # Read first 8KB
            for keyword in keywords:
                if re.search(keyword, content, re.MULTILINE):
                    return True
    except Exception:
        pass
    return False


def find_build_files(project_path, build_system):
    """Find all build files for a specific build system."""
    found_files = []
    
    for root, _, files in os.walk(project_path):
        # Skip common directories
        if any(skip in root for skip in ['.git', '.svn', 'node_modules', '__pycache__', 'build', 'dist']):
            continue
            
        for file in files:
            for pattern in build_system["patterns"]:
                if re.search(pattern, file):
                    file_path = os.path.join(root, file)
                    if check_file_content(file_path, build_system["keywords"]):
                        found_files.append(file_path)
                        break
    
    return found_files


def detect_build_system(project_path):
    """
    Detect the highest priority build system in the project.
    Returns: (build_system_name, [list of build files]) or (None, [])
    """
    if not os.path.isdir(project_path):
        return None, []
    
    # Sort by priority
    sorted_systems = sorted(BUILD_SYSTEMS, key=lambda x: x["priority"])
    
    for build_system in sorted_systems:
        files = find_build_files(project_path, build_system)
        if files:
            return build_system["name"], files
    
    return None, []


def main():
    if len(sys.argv) < 2:
        print("Usage: python detect_build_system.py <project_path>")
        sys.exit(1)
    
    project_path = sys.argv[1]
    build_system, files = detect_build_system(project_path)
    
    if build_system:
        print(f"Detected build system: {build_system}")
        print(f"Found {len(files)} build file(s):")
        for f in files:
            print(f"  - {f}")
    else:
        print("No supported build system detected")
        sys.exit(1)


if __name__ == "__main__":
    main()
