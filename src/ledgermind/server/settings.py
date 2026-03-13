"""
LedgerMind Settings Command - Manage configuration settings.

Usage:
    ledgermind settings show              # Show all current settings
    ledgermind settings get <key>         # Get specific setting value
    ledgermind settings set <key> <value> # Set specific setting value
    ledgermind settings reset <key>       # Reset specific setting to default
    ledgermind settings reset-all         # Reset all settings to defaults
"""

import argparse
import json
import os
import sys
from typing import Optional, Dict, Any, List

# Default settings with their types and descriptions
DEFAULT_SETTINGS = {
    "enrichment_mode": {
        "default": "rich",
        "choices": ["rich"],  # V7.8: lite removed, optimal reserved for future
        "description": "Enrichment mode (rich=full LLM enrichment with cloud API)"
    },
    "enrichment_language": {
        "default": "russian",
        "choices": None,  # Free text
        "description": "Language for LLM enrichment responses (e.g., 'russian', 'english')"
    },
    "enrichment_model": {
        "default": "gemini-2.5-flash-lite",
        "choices": None,
        "description": "LLM model for enrichment (when using rich mode)"
    },
    "merge_threshold": {
        "default": 0.85,
        "choices": None,
        "description": "Similarity threshold for merging duplicates (0.5-0.95)"
    },
    "embedder": {
        "default": "jina-v5-4bit",
        "choices": ["jina-v5-4bit", "custom"],
        "description": "Embedding model for vector search"
    },
    "client": {
        "default": "none",
        "choices": ["cursor", "claude", "gemini", "vscode", "none"],
        "description": "Client integration for context capture"
    },
}


def get_storage_path(custom_path: Optional[str] = None) -> str:
    """Determine storage path."""
    if custom_path:
        return os.path.abspath(custom_path)
    
    # Try default locations
    candidates = [
        os.path.abspath("../.ledgermind"),
        os.path.abspath(".ledgermind"),
        os.path.expanduser("~/.ledgermind"),
    ]
    
    for path in candidates:
        if os.path.exists(path):
            return path
    
    return candidates[0]  # Return first candidate even if doesn't exist


def load_settings(storage_path: str) -> Dict[str, Any]:
    """Load settings from storage."""
    # Try both possible locations for semantic_meta.db
    possible_paths = [
        os.path.join(storage_path, "semantic_meta.db"),
        os.path.join(storage_path, "semantic", "semantic_meta.db"),
    ]
    
    meta_db_path = None
    for path in possible_paths:
        if os.path.exists(path):
            meta_db_path = path
            break
    
    if not meta_db_path:
        return {}
    
    import sqlite3
    conn = sqlite3.connect(meta_db_path)
    conn.row_factory = sqlite3.Row
    
    settings = {}
    
    # Check which table exists
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='semantic_config'")
    if cursor.fetchone():
        # LedgerMind format: key|value in semantic_config table
        cursor = conn.execute("SELECT key, value FROM semantic_config")
        for row in cursor:
            key = row['key']
            value = row['value']
            if key in DEFAULT_SETTINGS:
                try:
                    settings[key] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    settings[key] = value
            else:
                settings[key] = value
    
    conn.close()
    
    # Fill in defaults for missing settings
    for key, config in DEFAULT_SETTINGS.items():
        if key not in settings:
            settings[key] = config['default']
    
    return settings


def save_setting(storage_path: str, key: str, value: Any) -> bool:
    """Save a single setting to storage using INSERT OR REPLACE."""
    # Try both possible locations
    possible_paths = [
        os.path.join(storage_path, "semantic_meta.db"),
        os.path.join(storage_path, "semantic", "semantic_meta.db"),
    ]
    
    meta_db_path = None
    for path in possible_paths:
        if os.path.exists(path):
            meta_db_path = path
            break
    
    if not meta_db_path:
        # Create the database if it doesn't exist
        from ledgermind.core.api.memory import Memory
        memory = Memory(storage_path=storage_path)
        memory.close()
        meta_db_path = os.path.join(storage_path, "semantic", "semantic_meta.db")
    
    import sqlite3
    try:
        conn = sqlite3.connect(meta_db_path)
        
        # Serialize value
        if isinstance(value, (dict, list, bool)):
            value_str = json.dumps(value)
        else:
            value_str = str(value)
        
        # Use INSERT OR REPLACE for semantic_config table
        conn.execute(
            "INSERT OR REPLACE INTO semantic_config (key, value) VALUES (?, ?)",
            (key, value_str)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error saving setting: {e}", file=sys.stderr)
        return False


def reset_setting(storage_path: str, key: str) -> bool:
    """Reset a single setting to default."""
    if key not in DEFAULT_SETTINGS:
        return False
    
    default_value = DEFAULT_SETTINGS[key]['default']
    return save_setting(storage_path, key, default_value)


def cmd_settings_show(storage_path: str, verbose: bool = False):
    """Show all current settings."""
    from rich.console import Console
    from rich.table import Table
    
    console = Console()
    settings = load_settings(storage_path)
    
    table = Table(title="LedgerMind Settings", show_header=True, header_style="bold cyan")
    table.add_column("Setting", style="green")
    table.add_column("Value", style="yellow")
    table.add_column("Default", style="dim")
    
    if verbose:
        table.add_column("Description", style="dim")
    
    for key, config in DEFAULT_SETTINGS.items():
        current = settings.get(key, config['default'])
        default = config['default']
        is_changed = current != default
        
        row = [
            key,
            f"[bold green]{current}[/]" if is_changed else str(current),
            str(default),
        ]
        
        if verbose:
            row.append(config['description'])
        
        table.add_row(*row)
    
    console.print(table)
    console.print(f"\nTotal: {len(settings)} settings configured")
    console.print("Use 'ledgermind settings set <key> <value>' to change a setting")


def cmd_settings_get(storage_path: str, key: str):
    """Get a specific setting value."""
    settings = load_settings(storage_path)
    
    if key not in settings and key not in DEFAULT_SETTINGS:
        print(f"Error: Unknown setting '{key}'", file=sys.stderr)
        print(f"Available settings: {', '.join(DEFAULT_SETTINGS.keys())}", file=sys.stderr)
        sys.exit(1)
    
    value = settings.get(key, DEFAULT_SETTINGS[key]['default'])
    print(value)


def cmd_settings_set(storage_path: str, key: str, value: str):
    """Set a specific setting value."""
    if key not in DEFAULT_SETTINGS:
        print(f"Error: Unknown setting '{key}'", file=sys.stderr)
        print(f"Available settings: {', '.join(DEFAULT_SETTINGS.keys())}", file=sys.stderr)
        sys.exit(1)
    
    config = DEFAULT_SETTINGS[key]
    
    # Validate choice
    if config['choices'] and value not in config['choices']:
        print(f"Error: Invalid value '{value}' for setting '{key}'", file=sys.stderr)
        print(f"Valid choices: {', '.join(config['choices'])}", file=sys.stderr)
        sys.exit(1)
    
    # Type conversion
    if isinstance(config['default'], float):
        try:
            value = float(value)
        except ValueError:
            print(f"Error: Value must be a number for setting '{key}'", file=sys.stderr)
            sys.exit(1)
    
    # Validate range for merge_threshold
    if key == "merge_threshold":
        if not 0.5 <= value <= 0.95:
            print(f"Error: merge_threshold must be between 0.5 and 0.95", file=sys.stderr)
            sys.exit(1)
    
    if save_setting(storage_path, key, value):
        print(f"✓ Setting '{key}' updated to '{value}'")
        
        # Show if restart is needed
        if key in ['enrichment_mode', 'embedder', 'enrichment_model']:
            print("⚠ Restart required: Run 'pkill -f background.py' and restart worker")
    else:
        sys.exit(1)


def cmd_settings_reset(storage_path: str, key: str):
    """Reset a specific setting to default."""
    if key not in DEFAULT_SETTINGS:
        print(f"Error: Unknown setting '{key}'", file=sys.stderr)
        print(f"Available settings: {', '.join(DEFAULT_SETTINGS.keys())}", file=sys.stderr)
        sys.exit(1)
    
    if reset_setting(storage_path, key):
        default = DEFAULT_SETTINGS[key]['default']
        print(f"✓ Setting '{key}' reset to default '{default}'")
    else:
        print(f"Error: Failed to reset setting '{key}'", file=sys.stderr)
        sys.exit(1)


def cmd_settings_reset_all(storage_path: str):
    """Reset all settings to defaults."""
    from rich.console import Console
    from rich.prompt import Confirm
    
    console = Console()
    
    if not Confirm.ask("This will reset ALL settings to defaults. Continue?"):
        console.print("Cancelled")
        return
    
    count = 0
    for key in DEFAULT_SETTINGS.keys():
        if reset_setting(storage_path, key):
            count += 1
    
    console.print(f"[green]✓[/] Reset {count} settings to defaults")
    console.print("⚠ Restart required: Run 'pkill -f background.py' and restart worker")


def create_settings_parser(subparsers):
    """Create the settings subcommand parser."""
    settings_parser = subparsers.add_parser(
        "settings",
        help="Manage LedgerMind configuration settings"
    )
    
    settings_subparsers = settings_parser.add_subparsers(
        dest="settings_command",
        help="Settings command to run"
    )
    
    # show command
    show_parser = settings_subparsers.add_parser(
        "show",
        help="Show all current settings"
    )
    show_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show descriptions for each setting"
    )
    
    # get command
    get_parser = settings_subparsers.add_parser(
        "get",
        help="Get a specific setting value"
    )
    get_parser.add_argument(
        "key",
        help="Setting key to get"
    )
    
    # set command
    set_parser = settings_subparsers.add_parser(
        "set",
        help="Set a specific setting value"
    )
    set_parser.add_argument(
        "key",
        help="Setting key to set"
    )
    set_parser.add_argument(
        "value",
        help="New value for the setting"
    )
    
    # reset command
    reset_parser = settings_subparsers.add_parser(
        "reset",
        help="Reset a specific setting to default"
    )
    reset_parser.add_argument(
        "key",
        help="Setting key to reset"
    )
    
    # reset-all command
    reset_all_parser = settings_subparsers.add_parser(
        "reset-all",
        help="Reset all settings to defaults"
    )
    
    # Common storage path argument
    for parser in [show_parser, get_parser, set_parser, reset_parser, reset_all_parser]:
        parser.add_argument(
            "--storage",
            type=str,
            default=None,
            help="Storage path (default: auto-detect)"
        )
    
    settings_parser.set_defaults(func=handle_settings_command)


def handle_settings_command(args):
    """Handle settings subcommand."""
    if not args.settings_command:
        print("Error: No settings command specified", file=sys.stderr)
        print("Use 'ledgermind settings --help' for available commands", file=sys.stderr)
        sys.exit(1)
    
    storage_path = get_storage_path(args.storage)
    
    if args.settings_command == "show":
        cmd_settings_show(storage_path, verbose=args.verbose)
    elif args.settings_command == "get":
        cmd_settings_get(storage_path, args.key)
    elif args.settings_command == "set":
        cmd_settings_set(storage_path, args.key, args.value)
    elif args.settings_command == "reset":
        cmd_settings_reset(storage_path, args.key)
    elif args.settings_command == "reset-all":
        cmd_settings_reset_all(storage_path)
    else:
        print(f"Error: Unknown settings command '{args.settings_command}'", file=sys.stderr)
        sys.exit(1)
