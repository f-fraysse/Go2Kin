#!/usr/bin/env python3
"""
Go2Kin - Multi-Camera GoPro Control Application
Main entry point for the GUI application

Usage: python go2kin.py
"""

import sys
import json
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

# Add code directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent))
# Add GUI module to path
sys.path.insert(0, str(Path(__file__).resolve().parent / 'GUI'))

# Path to app-level config (repo root)
APP_CONFIG_PATH = Path(__file__).resolve().parent.parent / "go2kin_config.json"


def load_app_config():
    """Load go2kin_config.json, adding missing fields with defaults."""
    default = {
        "data_root": "",
        "gopro_serial_numbers": [],
        "last_project": "",
        "last_session": "",
        "last_calibration": "",
    }
    try:
        if APP_CONFIG_PATH.exists():
            with open(APP_CONFIG_PATH, "r") as f:
                config = json.load(f)
            # Ensure new fields exist in old configs
            for key, value in default.items():
                config.setdefault(key, value)
            return config
    except Exception as e:
        print(f"Warning: Could not load {APP_CONFIG_PATH}: {e}")
    return dict(default)


def save_app_config(config):
    """Save go2kin_config.json."""
    try:
        with open(APP_CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Error saving config: {e}")


def validate_data_root(root, config):
    """Ensure data_root exists. Prompt user if not."""
    data_root = config.get("data_root", "")
    if data_root and Path(data_root).is_dir():
        return True

    # Hide the empty main window while showing the dialog
    root.withdraw()
    messagebox.showinfo(
        "Go2Kin - Data Root",
        "No data root folder is configured.\n\n"
        "Please select a folder where Go2Kin will store projects and data."
    )
    selected = filedialog.askdirectory(title="Select Go2Kin Data Root Folder")
    if not selected:
        root.destroy()
        print("No data root selected. Exiting.")
        sys.exit(0)

    config["data_root"] = selected
    Path(selected).mkdir(parents=True, exist_ok=True)
    save_app_config(config)
    root.deiconify()
    return True


def main():
    """Main application entry point"""
    try:
        from GUI import Go2KinMainWindow
        from project_manager import ProjectManager

        # Load app config and validate data root
        app_config = load_app_config()

        # Create the root window
        root = tk.Tk()

        # Set window icon (if available)
        try:
            pass
        except:
            pass

        # Validate data root (may show folder picker dialog)
        validate_data_root(root, app_config)

        # Save config (ensures new fields are persisted)
        save_app_config(app_config)

        # Instantiate ProjectManager
        pm = ProjectManager(app_config["data_root"])

        # Create the main application
        app = Go2KinMainWindow(
            root,
            project_manager=pm,
            app_config=app_config,
            app_config_path=APP_CONFIG_PATH,
        )

        # Start the GUI event loop
        root.mainloop()

    except ImportError as e:
        print(f"Error importing GUI modules: {e}")
        print("Make sure all required dependencies are installed:")
        print("- tkinter (usually included with Python)")
        print("- requests (for GoPro API communication)")
        sys.exit(1)
    except Exception as e:
        print(f"Error starting Go2Kin application: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("Go2Kin - Multi-Camera GoPro Control")
    print("====================================")
    print("Starting GUI application...")
    print()
    main()
