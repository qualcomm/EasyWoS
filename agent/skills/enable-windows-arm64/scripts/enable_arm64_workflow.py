#!/usr/bin/env python3
"""
Main workflow script to enable Windows ARM64 support in a project.
"""

import os
import sys
import subprocess
from pathlib import Path


def run_script(script_name, args):
    """Run a Python script and return success status."""
    script_dir = Path(__file__).parent
    script_path = script_dir / script_name
    
    cmd = [sys.executable, str(script_path)] + args
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return result.returncode == 0
    except Exception as e:
        print(f"Error running {script_name}: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python enable_arm64_workflow.py <project_path> [--no-backup]")
        print("\nThis script will:")
        print("  1. Detect the build system in your project")
        print("  2. Check if Windows ARM64 support already exists")
        print("  3. Add ARM64 support if not present")
        sys.exit(1)
    
    project_path = sys.argv[1]
    backup_flag = [] if "--no-backup" in sys.argv else []
    no_backup_flag = ["--no-backup"] if "--no-backup" in sys.argv else []
    
    if not os.path.isdir(project_path):
        print(f"Error: {project_path} is not a valid directory")
        sys.exit(1)
    
    print("=" * 60)
    print("Windows ARM64 Support Enabler")
    print("=" * 60)
    print()
    
    # Step 1: Detect build system
    print("Step 1: Detecting build system...")
    print("-" * 60)
    
    if not run_script("detect_build_system.py", [project_path]):
        print("\nError: Could not detect a supported build system")
        print("Supported: cmake, visual_studio, autotools, bazel, make, ninja, qmake, scons")
        sys.exit(1)
    
    # Parse detection output to get build system and files
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "detect_build_system.py"), project_path],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        sys.exit(1)
    
    # Extract build system and files from output
    lines = result.stdout.strip().split('\n')
    build_system = None
    build_files = []
    
    for line in lines:
        if line.startswith("Detected build system:"):
            build_system = line.split(":")[1].strip()
        elif line.strip().startswith("- "):
            build_files.append(line.strip()[2:])
    
    if not build_system or not build_files:
        print("Error: Could not parse build system detection results")
        sys.exit(1)
    
    print()
    
    # Step 2: Check ARM64 support
    print("Step 2: Checking for existing ARM64 support...")
    print("-" * 60)
    
    check_result = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "check_arm64_support.py"), 
         build_system] + build_files,
        capture_output=True,
        text=True
    )
    
    print(check_result.stdout)
    
    if check_result.returncode == 0:
        print("\n" + "=" * 60)
        print("✓ Windows ARM64 support is already enabled!")
        print("=" * 60)
        sys.exit(0)
    
    print()
    
    # Step 3: Add ARM64 support
    print("Step 3: Adding Windows ARM64 support...")
    print("-" * 60)
    
    # Map build system to enabler script
    enabler_map = {
        "cmake": "enable_cmake_arm64.py",
        "visual_studio": "enable_visual_studio_arm64.py",
        "make": "enable_make_arm64.py",
        "autotools": "enable_autotools_arm64.py",
        "bazel": "enable_bazel_arm64.py",
        "ninja": "enable_other_arm64.py",
        "qmake": "enable_other_arm64.py",
        "scons": "enable_other_arm64.py",
    }
    
    enabler_script = enabler_map.get(build_system)
    if not enabler_script:
        print(f"Error: No enabler script for {build_system}")
        sys.exit(1)
    
    # Process each build file
    success_count = 0
    for build_file in build_files:
        print(f"\nProcessing: {build_file}")
        if run_script(enabler_script, [build_file] + no_backup_flag):
            success_count += 1
    
    print()
    print("=" * 60)
    
    if success_count == len(build_files):
        print(f"✓ Successfully enabled ARM64 support in {success_count} file(s)")
        print("=" * 60)
        print("\nNext steps:")
        print("  1. Review the changes in your build files")
        print("  2. Test compilation with ARM64 toolchain")
        print("  3. Commit the changes to version control")
        sys.exit(0)
    else:
        print(f"⚠ Partially completed: {success_count}/{len(build_files)} files modified")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
