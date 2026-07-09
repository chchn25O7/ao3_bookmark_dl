import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

FORMAT_EXTENSIONS = {
    "PDF": "pdf",
    "EPUB": "epub",
    "MOBI": "mobi",
    "AZW3": "azw3",
    "HTML": "html",
}


@dataclass
class Config:
    username: str
    password: str
    formats: list = field(default_factory=lambda: ["PDF"])
    output_dir: str = "downloads"
    manifest_path: str = "manifest.json"
    delay: float = 5.0
    limit: int | None = None
    dry_run: bool = False
    force: bool = False
    headless: bool = False
    profile_dir: str = ".pw-profile"


def load_credentials() -> tuple[str, str]:
    load_dotenv()
    username = os.environ.get("AO3_USERNAME")
    password = os.environ.get("AO3_PASSWORD")
    if not username or not password:
        raise SystemExit(
            "AO3_USERNAME and AO3_PASSWORD must be set (copy .env.example to .env and fill them in)."
        )
    return username, password


def parse_formats(raw: str) -> list:
    formats = [f.strip().upper() for f in raw.split(",") if f.strip()]
    invalid = [f for f in formats if f not in FORMAT_EXTENSIONS]
    if invalid:
        raise SystemExit(
            f"Unknown format(s) {invalid}. Valid formats: {sorted(FORMAT_EXTENSIONS)}"
        )
    if not formats:
        raise SystemExit("At least one format must be specified.")
    return formats
