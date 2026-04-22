"""Environment variable support - load .env files for RPA scripts."""

import os


def load_env(env_path: str = None) -> dict:
    """Load environment variables from a .env file.

    Searches in order: given path, cwd/.env, ~/.actionshot/.env.
    Variables are set in os.environ AND returned as a dict.
    """
    search = [
        env_path,
        os.path.join(os.getcwd(), ".env"),
        os.path.join(os.path.expanduser("~"), ".actionshot", ".env"),
    ]

    for path in search:
        if path and os.path.exists(path):
            return _parse_env(path)

    return {}


def _parse_env(path: str) -> dict:
    """Parse a .env file and set variables in os.environ."""
    env_vars = {}

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if "=" not in line:
                continue

            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()

            # Remove surrounding quotes
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]

            env_vars[key] = value
            os.environ[key] = value

    return env_vars


def get_env(key: str, default: str = None) -> str:
    """Get an environment variable with fallback."""
    return os.environ.get(key, default)
