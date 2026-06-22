#!/usr/bin/env python3
"""
Add Windows ARM64 support to Visual Studio project files (.vcxproj and .sln).
"""

import os
import re
import sys
import shutil
import xml.etree.ElementTree as ET


def add_vcxproj_arm64(file_path, backup=True):
    """Add ARM64 configuration to .vcxproj file."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        if backup:
            backup_path = f"{file_path}.bak"
            shutil.copy2(file_path, backup_path)
            print(f"Backup created: {backup_path}")
        
        # Parse XML
        ET.register_namespace('', 'http://schemas.microsoft.com/developer/msbuild/2003')
        tree = ET.parse(file_path)
        root = tree.getroot()
        
        ns = {'': 'http://schemas.microsoft.com/developer/msbuild/2003'}
        
        # 1. Add ARM64 to ProjectConfigurations
        config_group = root.find(".//ItemGroup[@Label='ProjectConfigurations']", ns)
        if config_group is not None:
            # Check if ARM64 already exists
            existing_arm64 = config_group.findall(".//ProjectConfiguration[@Include]", ns)
            has_arm64 = any('ARM64' in cfg.get('Include', '') for cfg in existing_arm64)
            
            if not has_arm64:
                # Get existing configurations (Debug, Release, etc.)
                configs = set()
                for cfg in config_group.findall(".//ProjectConfiguration", ns):
                    include = cfg.get('Include', '')
                    if '|' in include:
                        config_name = include.split('|')[0]
                        configs.add(config_name)
                
                # Add ARM64 for each configuration
                for config_name in sorted(configs):
                    proj_config = ET.SubElement(config_group, 'ProjectConfiguration')
                    proj_config.set('Include', f'{config_name}|ARM64')
                    
                    config_elem = ET.SubElement(proj_config, 'Configuration')
                    config_elem.text = config_name
                    
                    platform_elem = ET.SubElement(proj_config, 'Platform')
                    platform_elem.text = 'ARM64'
        
        # 2. Add ARM64 PropertyGroups
        # Find existing PropertyGroups with Configuration conditions
        property_groups = root.findall(".//PropertyGroup[@Condition]", ns)
        
        # Get platform toolset from existing config
        platform_toolset = 'v143'  # Default
        for pg in property_groups:
            toolset_elem = pg.find('PlatformToolset', ns)
            if toolset_elem is not None and toolset_elem.text:
                platform_toolset = toolset_elem.text
                break
        
        print(f"  Using platform toolset: {platform_toolset}")
        
        # Find configurations to clone
        configs_to_add = []
        for pg in property_groups:
            condition = pg.get('Condition', '')
            if 'Win32' in condition or 'x64' in condition:
                # Extract configuration name (Debug/Release)
                match = re.search(r"'([^']+)\|", condition)
                if match:
                    config_name = match.group(1)
                    if not any(f'{config_name}|ARM64' in pg2.get('Condition', '') for pg2 in property_groups):
                        configs_to_add.append((config_name, pg))
        
        # Add ARM64 PropertyGroups
        for config_name, source_pg in configs_to_add:
            new_pg = ET.Element('PropertyGroup')
            new_pg.set('Condition', f"'$(Configuration)|$(Platform)'=='{config_name}|ARM64'")
            new_pg.set('Label', 'Configuration')
            
            # Copy relevant elements
            for child in source_pg:
                if child.tag.endswith('ConfigurationType') or child.tag.endswith('PlatformToolset') or \
                   child.tag.endswith('CharacterSet') or child.tag.endswith('UseDebugLibraries'):
                    new_child = ET.Element(child.tag)
                    new_child.text = child.text
                    new_child.attrib = child.attrib.copy()
                    new_pg.append(new_child)
            
            # Ensure PlatformToolset exists
            if new_pg.find('PlatformToolset', ns) is None:
                toolset_elem = ET.SubElement(new_pg, 'PlatformToolset')
                toolset_elem.text = platform_toolset
            
            # Insert after source PropertyGroup
            parent = root
            index = list(parent).index(source_pg) + 1
            parent.insert(index, new_pg)
        
        if configs_to_add:
            print(f"  Added {len(configs_to_add)} ARM64 PropertyGroups")
        
        # 3. Add ARM64 ItemDefinitionGroups (CRITICAL for build settings)
        item_def_groups = root.findall(".//ItemDefinitionGroup[@Condition]", ns)
        
        idg_configs_to_add = []
        for idg in item_def_groups:
            condition = idg.get('Condition', '')
            if 'Win32' in condition or 'x64' in condition:
                match = re.search(r"'([^']+)\|", condition)
                if match:
                    config_name = match.group(1)
                    if not any(f'{config_name}|ARM64' in idg2.get('Condition', '') for idg2 in item_def_groups):
                        idg_configs_to_add.append((config_name, idg))
        
        # Add ARM64 ItemDefinitionGroups
        import copy
        for config_name, source_idg in idg_configs_to_add:
            new_idg = ET.Element('ItemDefinitionGroup')
            new_idg.set('Condition', f"'$(Configuration)|$(Platform)'=='{config_name}|ARM64'")
            
            # Deep copy all children (ClCompile, Link, etc.)
            for child in source_idg:
                new_child = copy.deepcopy(child)
                new_idg.append(new_child)
            
            # Insert after source ItemDefinitionGroup
            parent = root
            index = list(parent).index(source_idg) + 1
            parent.insert(index, new_idg)
        
        if idg_configs_to_add:
            print(f"  Added {len(idg_configs_to_add)} ARM64 ItemDefinitionGroups")
        
        # Write back with proper formatting
        tree.write(file_path, encoding='utf-8', xml_declaration=True)
        
        print(f"✓ Modified: {file_path}")
        
        # Verify the changes
        verify_arm64_support(file_path)
        
        # Check for dependency warnings
        check_dependency_paths(file_path)
        
        return True
    
    except Exception as e:
        print(f"✗ Error modifying {file_path}: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_arm64_support(file_path):
    """Verify ARM64 was added correctly to .vcxproj."""
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        ns = {'': 'http://schemas.microsoft.com/developer/msbuild/2003'}
        
        checks = {
            'ProjectConfiguration': False,
            'PropertyGroup': False,
            'ItemDefinitionGroup': False
        }
        
        # Check ProjectConfiguration
        configs = root.findall(".//ProjectConfiguration[@Include]", ns)
        checks['ProjectConfiguration'] = any('ARM64' in c.get('Include', '') for c in configs)
        
        # Check PropertyGroup
        pgs = root.findall(".//PropertyGroup[@Condition]", ns)
        checks['PropertyGroup'] = any('ARM64' in pg.get('Condition', '') for pg in pgs)
        
        # Check ItemDefinitionGroup
        idgs = root.findall(".//ItemDefinitionGroup[@Condition]", ns)
        checks['ItemDefinitionGroup'] = any('ARM64' in idg.get('Condition', '') for idg in idgs)
        
        print("\n  Verification:")
        all_passed = True
        for check, passed in checks.items():
            status = "✓" if passed else "✗"
            print(f"    {status} {check}")
            if not passed:
                all_passed = False
        
        if not all_passed:
            print("\n  ⚠️  Warning: Some ARM64 configurations may be incomplete")
        
        return all_passed
    except Exception as e:
        print(f"  ⚠️  Could not verify: {e}")
        return False


def check_dependency_paths(file_path):
    """Check for dependency path issues that may need manual adjustment."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        issues = []
        
        # Check for $(PlatformName) in paths
        if re.search(r'\$\([A-Z_]+\).*\$\(PlatformName\)', content):
            issues.append({
                'type': 'platform_path',
                'message': 'Found $(PlatformName) in dependency paths',
                'suggestion': 'ARM64 dependencies may need different path structure'
            })
        
        # Check for common dependency variables
        dep_vars = ['APR_DIST', 'OPENSSL_DIST', 'BOOST_ROOT', 'QT_DIR', 'ZLIB_ROOT']
        found_deps = []
        for var in dep_vars:
            if f'$({var})' in content:
                found_deps.append(var)
        
        if found_deps:
            issues.append({
                'type': 'dependencies',
                'variables': found_deps,
                'message': f'Project uses external dependencies: {", ".join(found_deps)}',
                'suggestion': 'Ensure ARM64 versions are available and paths are set correctly'
            })
        
        if issues:
            print("\n  ⚠️  Dependency Warnings:")
            for issue in issues:
                print(f"    - {issue['message']}")
                print(f"      → {issue['suggestion']}")
                if 'variables' in issue:
                    print(f"      → Set environment variables:")
                    for var in issue['variables']:
                        print(f"        $env:{var} = \"C:\\path\\to\\{var.lower()}-arm64\"")
        
        return issues
    except Exception as e:
        print(f"  ⚠️  Could not check dependencies: {e}")
        return []


def add_sln_arm64(file_path, backup=True):
    """Add ARM64 platform to .sln file."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        if backup:
            backup_path = f"{file_path}.bak"
            shutil.copy2(file_path, backup_path)
            print(f"Backup created: {backup_path}")
        
        # Check if ARM64 already exists
        if 'ARM64' in content:
            print(f"ARM64 already exists in {file_path}")
            return True
        
        modified = False
        lines = content.split('\n')
        new_lines = []
        
        for i, line in enumerate(lines):
            new_lines.append(line)
            
            # Add ARM64 after Win32 or x64 platform declarations
            if 'GlobalSection(SolutionConfigurationPlatforms)' in line:
                # Find all configuration lines
                j = i + 1
                configs = []
                while j < len(lines) and 'EndGlobalSection' not in lines[j]:
                    if '=' in lines[j]:
                        config_line = lines[j].strip()
                        if 'Win32' in config_line or 'x64' in config_line:
                            # Create ARM64 version
                            arm64_line = config_line.replace('Win32', 'ARM64').replace('x64', 'ARM64')
                            if arm64_line not in configs:
                                configs.append(arm64_line)
                    j += 1
                
                # Insert ARM64 configs
                for config in configs:
                    new_lines.append('\t\t' + config)
                    modified = True
            
            # Add ARM64 project configurations
            elif '.ActiveCfg = ' in line or '.Build.0 = ' in line:
                if 'Win32' in line or 'x64' in line:
                    arm64_line = line.replace('Win32', 'ARM64').replace('x64', 'ARM64')
                    new_lines.append(arm64_line)
                    modified = True
        
        if modified:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(new_lines))
            print(f"✓ Modified: {file_path}")
            return True
        else:
            print(f"No modifications needed for {file_path}")
            return True
    
    except Exception as e:
        print(f"✗ Error modifying {file_path}: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python enable_visual_studio_arm64.py <file_path> [--no-backup]")
        print("\nSupported files:")
        print("  - .vcxproj (Visual Studio project)")
        print("  - .sln (Visual Studio solution)")
        sys.exit(1)
    
    file_path = sys.argv[1]
    backup = "--no-backup" not in sys.argv
    
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
    
    print(f"\nProcessing: {file_path}")
    print("=" * 60)
    
    if file_path.endswith('.vcxproj'):
        success = add_vcxproj_arm64(file_path, backup)
    elif file_path.endswith('.sln'):
        success = add_sln_arm64(file_path, backup)
    else:
        print(f"Unsupported file type: {file_path}")
        print("Supported: .vcxproj, .sln")
        sys.exit(1)
    
    if success:
        print("\n" + "=" * 60)
        print("✓ ARM64 support added successfully")
        print("=" * 60)
        print("\nNext steps:")
        print("  1. Open the solution in Visual Studio 2022")
        print("  2. Select 'ARM64' platform from the dropdown")
        print("  3. Select configuration (e.g., Release)")
        print("  4. Build → Build Solution")
        print("\nIf build fails:")
        print("  - Check that all dependencies are built for ARM64")
        print("  - Verify environment variables point to ARM64 versions")
        print("  - Review dependency warnings above")
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
