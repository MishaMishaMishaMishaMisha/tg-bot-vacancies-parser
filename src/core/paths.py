import os

from pathlib import Path


# find project root by "pyproject.toml" file
def find_project_root() -> Path:
    
    current = Path(__file__).resolve().parent
    full_path = [current, *current.parents]

    for directory in full_path:
        if (directory / "pyproject.toml").is_file():
            return directory

    raise RuntimeError("Project root not found")


BASE_DIR = find_project_root()
ENV_FILE_PATH = BASE_DIR / ".env"
