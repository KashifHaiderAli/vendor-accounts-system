from pathlib import Path


def ensure_folder(path: str | Path) -> Path:
    folder = Path(path)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def db_path_from_folder(folder: str | Path, file_name: str) -> Path:
    return Path(folder) / file_name

