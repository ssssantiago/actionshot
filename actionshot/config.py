"""Config file support - load settings from actionshot.yaml."""

import os

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


DEFAULT_CONFIG = {
    "output_dir": "recordings",
    "video": False,
    "video_fps": 10,
    "ocr": True,
    "image_format": "jpeg",
    "image_quality": 85,
    "scroll_debounce": 0.3,
    "key_flush_delay": 0.8,
    "min_click_interval": 0.15,
    "drag_threshold": 10,
    "hotkeys": {
        "toggle": "win+shift+r",
        "pause": "win+shift+p",
    },
}

CONFIG_FILENAME = "actionshot.yaml"
CONFIG_SEARCH_PATHS = [
    ".",
    os.path.expanduser("~"),
    os.path.join(os.path.expanduser("~"), ".actionshot"),
]


def find_config() -> str | None:
    """Search for actionshot.yaml in common locations."""
    for directory in CONFIG_SEARCH_PATHS:
        path = os.path.join(directory, CONFIG_FILENAME)
        if os.path.exists(path):
            return path
    return None


def load_config(path: str = None) -> dict:
    """Load config from YAML file, merged with defaults."""
    config = dict(DEFAULT_CONFIG)

    if path is None:
        path = find_config()

    if path and os.path.exists(path):
        if not HAS_YAML:
            print(f"  Warning: Found {path} but PyYAML not installed. Using defaults.")
            return config

        with open(path, "r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}

        # Merge (shallow — nested dicts like hotkeys get replaced entirely)
        for key, value in user_config.items():
            if key in config:
                config[key] = value

        print(f"  Config loaded: {path}")

    return config


def create_default_config(path: str = None):
    """Create a default actionshot.yaml file."""
    if path is None:
        path = os.path.join(".", CONFIG_FILENAME)

    if not HAS_YAML:
        # Write manually without yaml dependency
        content = """# ActionShot configuration
output_dir: recordings
video: false
video_fps: 10
ocr: true
image_format: jpeg    # jpeg or png
image_quality: 85     # 1-100, only for jpeg
scroll_debounce: 0.3  # seconds
key_flush_delay: 0.8  # seconds
min_click_interval: 0.15  # seconds between clicks
drag_threshold: 10    # pixels

hotkeys:
  toggle: win+shift+r
  pause: win+shift+p
"""
    else:
        import yaml
        content = yaml.dump(DEFAULT_CONFIG, default_flow_style=False, sort_keys=False)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"  Config created: {path}")
    return path
