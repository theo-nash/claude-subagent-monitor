#!/usr/bin/env python3
"""
Self-contained installer for Claude Subagent Monitoring System.
Everything goes into a single subagent-monitor directory.
"""

import os
import json
import shutil
import sys
from pathlib import Path

def create_self_contained_dir(install_location='global'):
    """Create the self-contained subagent-monitor directory."""
    if install_location == 'global':
        base_dir = Path.home() / '.claude'
        print(f"📍 Installing globally to: ~/.claude/subagent-monitor/")
    else:
        base_dir = Path('.claude')
        print(f"📍 Installing to project: ./.claude/subagent-monitor/")
    
    base_dir.mkdir(exist_ok=True)
    monitor_dir = base_dir / 'subagent-monitor'
    
    # Remove old installation if exists
    if monitor_dir.exists():
        backup = monitor_dir.with_suffix('.backup')
        if backup.exists():
            shutil.rmtree(backup)
        shutil.move(str(monitor_dir), str(backup))
        print(f"   Backed up existing installation")
    
    # Create fresh directory structure
    monitor_dir.mkdir()
    (monitor_dir / 'hooks').mkdir()
    (monitor_dir / 'lib').mkdir()
    (monitor_dir / 'data').mkdir()
    (monitor_dir / 'bin').mkdir()
    
    print(f"✓ Created self-contained directory: {monitor_dir}")
    return base_dir, monitor_dir

def copy_all_files(source_dir: Path, monitor_dir: Path, base_dir: Path):
    """Copy all necessary files to the self-contained directory."""
    
    # Copy the package files to lib/
    lib_dir = monitor_dir / 'lib'
    source_package = source_dir / 'template'
    
    print("\n📦 Installing package files...")
    for py_file in source_package.glob('*.py'):
        dest_file = lib_dir / py_file.name
        shutil.copy2(py_file, dest_file)
        dest_file.chmod(0o644)
        print(f"   ✓ {py_file.name}")
    
    # Create hook entry points in hooks/
    hooks_dir = monitor_dir / 'hooks'
    
    print("\n🔗 Creating hook entry points...")
    
    # PreToolUse hook
    pretooluse_content = f"""#!/usr/bin/env python3
import sys
import os

# Add lib directory to path and set data directory
sys.path.insert(0, '{lib_dir}')
os.environ['SUBAGENT_DATA_DIR'] = '{monitor_dir / "data"}'

from pretooluse_subagent_tracker import main
if __name__ == "__main__":
    main()
"""
    (hooks_dir / 'pretooluse.py').write_text(pretooluse_content)
    (hooks_dir / 'pretooluse.py').chmod(0o755)
    print("   ✓ pretooluse.py")
    
    # SubagentStop hook
    subagentstop_content = f"""#!/usr/bin/env python3
import sys
import os

# Add lib directory to path and set data directory
sys.path.insert(0, '{lib_dir}')
os.environ['SUBAGENT_DATA_DIR'] = '{monitor_dir / "data"}'

from subagentstop_tracker import main
if __name__ == "__main__":
    main()
"""
    (hooks_dir / 'subagentstop.py').write_text(subagentstop_content)
    (hooks_dir / 'subagentstop.py').chmod(0o755)
    print("   ✓ subagentstop.py")
    
    # Create query command in bin/
    bin_dir = monitor_dir / 'bin'
    query_content = f"""#!/usr/bin/env python3
import sys
import os

# Add lib to path
sys.path.insert(0, '{lib_dir}')

# Override default paths to use our data directory
os.environ['SUBAGENT_DATA_DIR'] = '{monitor_dir / "data"}'

from database_utils import SubagentTracker
from active_subagent_tracker import ActiveSubagentTracker

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Query subagent tracking data')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    active_parser = subparsers.add_parser('active', help='List active subagents')
    status_parser = subparsers.add_parser('status', help='System status')
    
    args = parser.parse_args()
    
    if args.command == 'active':
        tracker = SubagentTracker()
        active = tracker.get_active_subagents()
        
        if active:
            print(f"\\n🤖 Active Subagents ({{len(active)}}):")
            for sub in active:
                print(f"  • {{sub['subagent_type']}} (session: {{sub['session_id'][:8]}}...)")
                print(f"    Started: {{sub.get('start_time', 'unknown')}}")
        else:
            print("No active subagents")
    
    elif args.command == 'status':
        tracker = SubagentTracker()
        active_db = tracker.get_active_subagents()
        
        active_tracker = ActiveSubagentTracker()
        summary = active_tracker.get_tracking_summary()
        
        print("\\n📊 System Status:")
        print(f"  Database: {{len(active_db)}} active")
        print(f"  Tracker: {{summary.get('active', 0)}} active, {{summary.get('completing', 0)}} completing")
        print(f"  Data location: {monitor_dir / 'data'}")
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
"""
    
    (bin_dir / 'subagent-query').write_text(query_content)
    (bin_dir / 'subagent-query').chmod(0o755)
    print("\n📟 Created query command: bin/subagent-query")
    
    # Create convenient symlink in base .claude directory
    symlink_path = base_dir / 'subagent'
    if symlink_path.exists():
        symlink_path.unlink()
    symlink_path.symlink_to(bin_dir / 'subagent-query')
    print(f"   ✓ Created symlink: {symlink_path} -> bin/subagent-query")
    
    # Create developer symlinks for easy library access
    print("\n🔗 Creating developer symlinks...")
    
    # MCP context for MCP developers
    mcp_link = base_dir / 'mcp_context.py'
    if mcp_link.exists():
        mcp_link.unlink()
    try:
        mcp_link.symlink_to(lib_dir / 'mcp_context.py')
        print(f"   ✓ {mcp_link.name} -> lib/mcp_context.py")
    except OSError:
        # Fallback to copying on Windows or if symlinks not supported
        shutil.copy2(lib_dir / 'mcp_context.py', mcp_link)
        print(f"   ✓ {mcp_link.name} (copied)")
    
    # Subagent context for hook developers
    subagent_link = base_dir / 'subagent_context.py'
    if subagent_link.exists():
        subagent_link.unlink()
    try:
        subagent_link.symlink_to(lib_dir / 'subagent_context.py')
        print(f"   ✓ {subagent_link.name} -> lib/subagent_context.py")
    except OSError:
        shutil.copy2(lib_dir / 'subagent_context.py', subagent_link)
        print(f"   ✓ {subagent_link.name} (copied)")
    
    # MCP correlation service for advanced users
    correlation_link = base_dir / 'mcp_correlation_service.py'
    if correlation_link.exists():
        correlation_link.unlink()
    try:
        correlation_link.symlink_to(lib_dir / 'mcp_correlation_service.py')
        print(f"   ✓ {correlation_link.name} -> lib/mcp_correlation_service.py")
    except OSError:
        shutil.copy2(lib_dir / 'mcp_correlation_service.py', correlation_link)
        print(f"   ✓ {correlation_link.name} (copied)")
    
    print("\n📚 Developer files available at:")
    print(f"   • {base_dir}/mcp_context.py - MCP context helper")
    print(f"   • {base_dir}/subagent_context.py - Subagent detection")
    print(f"   • {base_dir}/mcp_correlation_service.py - Correlation engine")
    
    return base_dir

def update_data_paths(monitor_dir: Path):
    """Update the database and tracker modules to use the data directory."""
    lib_dir = monitor_dir / 'lib'
    data_dir = monitor_dir / 'data'
    
    print("\n🔧 Configuring data paths...")
    
    # Update database_utils.py
    db_utils = lib_dir / 'database_utils.py'
    content = db_utils.read_text()
    
    # Replace the __init__ method to use our data directory
    old_init = '''    def __init__(self, db_path: str = None):
        """Initialize the subagent tracker with database path."""
        if db_path is None:
            # Check for global installation first
            global_claude_dir = os.path.expanduser('~/.claude')
            if os.path.exists(global_claude_dir):
                claude_dir = global_claude_dir
            else:
                # Fall back to project-specific
                claude_dir = os.path.join(os.getcwd(), '.claude')
            
            os.makedirs(claude_dir, exist_ok=True)
            db_path = os.path.join(claude_dir, 'subagents.db')'''
    
    new_init = f"""    def __init__(self, db_path: str = None):
        \"\"\"Initialize the subagent tracker with database path.\"\"\"
        if db_path is None:
            # Use environment variable if set, otherwise use our data directory
            data_dir = os.environ.get('SUBAGENT_DATA_DIR', '{data_dir}')
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, 'subagents.db')"""
    
    content = content.replace(old_init, new_init)
    db_utils.write_text(content)
    
    # Update active_subagent_tracker.py
    tracker = lib_dir / 'active_subagent_tracker.py'
    content = tracker.read_text()
    
    old_init = '''    def __init__(self, state_file: str = None):
        if state_file is None:
            # Check for global installation first
            global_claude_dir = os.path.expanduser('~/.claude')
            if os.path.exists(global_claude_dir):
                claude_dir = global_claude_dir
            else:
                # Fall back to project-specific
                claude_dir = os.path.join(os.getcwd(), '.claude')
            
            os.makedirs(claude_dir, exist_ok=True)
            state_file = os.path.join(claude_dir, 'active_subagents.json')'''
    
    new_init = f"""    def __init__(self, state_file: str = None):
        if state_file is None:
            # Use environment variable if set, otherwise use our data directory
            data_dir = os.environ.get('SUBAGENT_DATA_DIR', '{data_dir}')
            os.makedirs(data_dir, exist_ok=True)
            state_file = os.path.join(data_dir, 'active_subagents.json')"""
    
    content = content.replace(old_init, new_init)
    tracker.write_text(content)
    
    print("   ✓ Configured to use data directory")

def update_settings(base_dir: Path, monitor_dir: Path, install_location: str):
    """Update settings.json or settings.local.json with hook paths."""
    
    if install_location == 'project':
        settings_path = base_dir / 'settings.local.json'
        print(f"\n📝 Updating project settings: {settings_path.name}")
    else:
        settings_path = base_dir / 'settings.json'
        print(f"\n📝 Updating global settings: {settings_path.name}")
    
    # Hook paths point to our self-contained directory
    hooks_path = monitor_dir / 'hooks'
    
    new_hooks = {
        "PreToolUse": [
            {
                "matcher": "Task",
                "hooks": [
                    {
                        "type": "command",
                        "command": f"python3 {hooks_path}/pretooluse.py",
                        "timeout": 10
                    }
                ]
            },
            {
                "matcher": "mcp.*",
                "hooks": [
                    {
                        "type": "command",
                        "command": f"python3 {hooks_path}/pretooluse.py",
                        "timeout": 10
                    }
                ]
            }
        ],
        "SubagentStop": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": f"python3 {hooks_path}/subagentstop.py",
                        "timeout": 30
                    }
                ]
            }
        ]
    }
    
    # Load or create settings
    if settings_path.exists():
        with open(settings_path, 'r') as f:
            settings = json.load(f)
        # Backup
        backup_path = settings_path.with_suffix('.json.backup')
        shutil.copy2(settings_path, backup_path)
        print(f"   Backed up to {backup_path.name}")
    else:
        settings = {}
    
    # Update hooks - preserve existing hooks, only update our own
    if 'hooks' not in settings:
        settings['hooks'] = {}
    
    for hook_type, new_hook_configs in new_hooks.items():
        if hook_type not in settings['hooks']:
            settings['hooks'][hook_type] = []
        
        # Remove old subagent-monitor hooks (if any)
        existing_hooks = settings['hooks'][hook_type]
        filtered_hooks = []
        
        for hook_config in existing_hooks:
            # Check if this is our hook by looking for subagent-monitor in the command
            if 'hooks' in hook_config:
                is_ours = False
                for hook in hook_config.get('hooks', []):
                    command = hook.get('command', '')
                    if 'subagent-monitor' in command:
                        is_ours = True
                        break
                
                if not is_ours:
                    # Keep hooks from other tools
                    filtered_hooks.append(hook_config)
            else:
                # Keep hooks with different structure
                filtered_hooks.append(hook_config)
        
        # Add our new hook configs
        filtered_hooks.extend(new_hook_configs)
        settings['hooks'][hook_type] = filtered_hooks
        
        print(f"   ✓ Updated {hook_type} hook (preserved {len(filtered_hooks) - len(new_hook_configs)} existing hooks)")
    
    # Save settings
    with open(settings_path, 'w') as f:
        json.dump(settings, f, indent=2)
    
    print(f"   ✓ Saved {settings_path.name}")

def create_readme(monitor_dir: Path):
    """Create a README in the monitor directory."""
    readme_content = """# Subagent Monitor Directory

This is a self-contained installation of the Claude Subagent Monitoring System.

## Directory Structure
```
subagent-monitor/
├── hooks/          # Hook entry points
├── lib/            # Python modules
├── data/           # Database and state files
├── bin/            # Query commands
└── README.md       # This file
```

## Usage
- Query active subagents: `./bin/subagent-query active`
- Check status: `./bin/subagent-query status`

## Uninstall
To completely remove the monitoring system:
1. Delete this directory
2. Remove hook entries from settings.json or settings.local.json

## Data
All data (database, active tracker state) is stored in the `data/` subdirectory.
"""
    
    (monitor_dir / 'README.md').write_text(readme_content)
    print("\n📄 Created README.md")

def verify_installation(base_dir: Path, monitor_dir: Path, install_location: str):
    """Verify the installation."""
    print("\n🔍 Verifying installation...")
    
    if install_location == 'project':
        settings_file = base_dir / 'settings.local.json'
    else:
        settings_file = base_dir / 'settings.json'
    
    checks = {
        'monitor directory': monitor_dir.exists(),
        'hooks directory': (monitor_dir / 'hooks').exists(),
        'lib directory': (monitor_dir / 'lib').exists(),
        'data directory': (monitor_dir / 'data').exists(),
        'bin directory': (monitor_dir / 'bin').exists(),
        'pretooluse hook': (monitor_dir / 'hooks' / 'pretooluse.py').exists(),
        'subagentstop hook': (monitor_dir / 'hooks' / 'subagentstop.py').exists(),
        'query command': (monitor_dir / 'bin' / 'subagent-query').exists(),
        'settings updated': settings_file.exists(),
    }
    
    all_good = True
    for item, exists in checks.items():
        status = "✓" if exists else "✗"
        print(f"   {status} {item}")
        if not exists:
            all_good = False
    
    return all_good

def uninstall(install_location='global'):
    """Uninstall the monitoring system cleanly."""
    if install_location == 'global':
        base_dir = Path.home() / '.claude'
        settings_path = base_dir / 'settings.json'
    else:
        base_dir = Path('.claude')
        settings_path = base_dir / 'settings.local.json'
    
    monitor_dir = base_dir / 'subagent-monitor'
    
    print("🗑️  Uninstalling Claude Subagent Monitoring System")
    print("=" * 50)
    
    # Remove hooks from settings
    if settings_path.exists():
        with open(settings_path, 'r') as f:
            settings = json.load(f)
        
        if 'hooks' in settings:
            for hook_type in ['PreToolUse', 'SubagentStop']:
                if hook_type in settings['hooks']:
                    original_count = len(settings['hooks'][hook_type])
                    # Filter out our hooks
                    filtered = []
                    for hook_config in settings['hooks'][hook_type]:
                        is_ours = False
                        if 'hooks' in hook_config:
                            for hook in hook_config.get('hooks', []):
                                if 'subagent-monitor' in hook.get('command', ''):
                                    is_ours = True
                                    break
                        if not is_ours:
                            filtered.append(hook_config)
                    
                    settings['hooks'][hook_type] = filtered
                    removed_count = original_count - len(filtered)
                    if removed_count > 0:
                        print(f"   ✓ Removed {removed_count} {hook_type} hook(s)")
        
        # Save updated settings
        with open(settings_path, 'w') as f:
            json.dump(settings, f, indent=2)
        print(f"   ✓ Updated {settings_path.name}")
    
    # Remove symlinks
    symlinks = [
        base_dir / 'subagent',
        base_dir / 'mcp_context.py',
        base_dir / 'subagent_context.py', 
        base_dir / 'mcp_correlation_service.py'
    ]
    
    for symlink in symlinks:
        if symlink.exists():
            symlink.unlink()
            print(f"   ✓ Removed {symlink.name}")
    
    # Remove monitor directory
    if monitor_dir.exists():
        shutil.rmtree(monitor_dir)
        print(f"   ✓ Removed {monitor_dir}")
    
    print("\n✅ Uninstallation complete!")
    print("\nThe monitoring system has been removed.")
    print("Your other hooks and settings remain intact.")

def main():
    """Main installation function."""
    print("🚀 Claude Subagent Monitoring - Self-Contained Installer")
    print("=" * 58)
    
    source_dir = Path(__file__).parent
    
    # Check for source files
    if not (source_dir / 'template').exists():
        print("\n❌ Error: template package not found!")
        sys.exit(1)
    
    # Installation type
    print("\n📋 Installation Options:")
    print("1. Install globally (~/.claude/subagent-monitor/)")
    print("2. Install to project (./.claude/subagent-monitor/)")
    print("3. Uninstall")
    
    choice = input("\nSelect [1/2/3] (default: 1): ").strip() or '1'
    
    if choice == '3':
        # Uninstall
        print("\n🔍 Checking for installations...")
        global_exists = (Path.home() / '.claude' / 'subagent-monitor').exists()
        local_exists = (Path('.claude') / 'subagent-monitor').exists()
        
        if global_exists and local_exists:
            print("Found both global and project installations.")
            uninstall_choice = input("Uninstall [g]lobal, [p]roject, or [b]oth? ").lower()
            if uninstall_choice == 'p':
                uninstall('project')
            elif uninstall_choice == 'b':
                uninstall('global')
                uninstall('project')
            else:
                uninstall('global')
        elif global_exists:
            uninstall('global')
        elif local_exists:
            uninstall('project')
        else:
            print("\n❌ No installation found.")
        return
    
    if choice == '2':
        install_location = 'project'
    else:
        install_location = 'global'
    
    try:
        # Create self-contained directory
        base_dir, monitor_dir = create_self_contained_dir(install_location)
        
        # Copy all files
        copy_all_files(source_dir, monitor_dir, base_dir)
        
        # Update data paths
        update_data_paths(monitor_dir)
        
        # Update settings
        update_settings(base_dir, monitor_dir, install_location)
        
        # Create README
        create_readme(monitor_dir)
        
        # Verify
        if verify_installation(base_dir, monitor_dir, install_location):
            print("\n✅ Installation Complete!")
        else:
            print("\n⚠️  Installation completed with issues")
        
        print(f"\n📁 Everything installed to: {monitor_dir}")
        print("\n📋 Next Steps:")
        print("1. Restart Claude Code for hooks to take effect")
        print("2. Use subagents - they'll be tracked automatically")
        print(f"3. Query: {monitor_dir}/bin/subagent-query active")
        print(f"4. Status: {monitor_dir}/bin/subagent-query status")
        
        print("\n✨ Benefits of self-contained installation:")
        print("• Everything in ONE directory")
        print("• Easy to find, backup, or remove")
        print("• No pollution of hooks directory")
        print("• Data stored within the monitor directory")
        
    except Exception as e:
        print(f"\n❌ Installation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()