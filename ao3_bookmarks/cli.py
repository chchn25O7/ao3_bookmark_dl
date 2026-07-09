import argparse
import logging

from .browser import Browser
from .config import Config, load_credentials, parse_formats
from .downloader import run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ao3_bookmarks",
        description="Download ao3 bookmarks.",
    )
    parser.add_argument(
        "--formats", default="PDF",
        help="List of formats to download, separate by comma: PDF, EPUB, MOBI, AZW3, HTML (default: PDF)",
    )
    parser.add_argument(
        "--output-dir", default="downloads", help="Location where downloaded works will go"
    )
    parser.add_argument(
        "--manifest", default="manifest.json", help="Manifest file location (previous download history)"
    )
    parser.add_argument(
        "--delay", type=float, default=5.0,
        help="Seconds between each request, excluding sleeps and jitter (default and recommended minimum: 5.0)",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Only download the first N bookmarks"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Redownload everything, irrespective if it's been downloaded before",
    )
    parser.add_argument(
        "--profile-dir", default=".pw-profile",
        help="Directory for the persistent browser profile that keeps you logged in between runs (default: .pw-profile)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable extra debug messages."
    )
    return parser


def main():
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    username, password = load_credentials()
    config = Config(
        username=username,
        password=password,
        formats=parse_formats(args.formats),
        output_dir=args.output_dir,
        manifest_path=args.manifest,
        delay=args.delay,
        limit=args.limit,
        force=args.force,
        profile_dir=args.profile_dir,
    )

    browser = Browser(config.profile_dir, delay=config.delay)

    try:
        summary = run(config, browser)
    finally:
        browser.close()

    print("\n--- Summary ---")
    print(f"Downloaded:               {summary.downloaded}")
    print(f"Already had:              {summary.already_had}")
    print(f"Skipped because deleted:  {summary.skipped_deleted}")
    print(f"Skipped because series:   {summary.skipped_series}")
    print(f"Ao3 download error:       {summary.skipped_format}")
    print(f"Browser error:            {summary.errored}")


if __name__ == "__main__":
    main()
