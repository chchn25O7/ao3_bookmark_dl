import logging
import os
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin

from .bookmarks import backoff_seconds, iter_bookmarked_works
from .browser import RETRYABLE_STATUSES, Browser
from .config import Config, FORMAT_EXTENSIONS
from .manifest import Manifest

log = logging.getLogger("ao3_bookmarks")

MAX_WORK_ATTEMPTS = 5
ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WORK_URL = "https://archiveofourown.org/works/{id}?view_adult=true&view_full_work=true"


@dataclass
class Summary:
    downloaded: int = 0
    already_had: int = 0
    skipped_deleted: int = 0
    skipped_series: int = 0
    errored: int = 0
    skipped_format: int = 0
    processed_works: set = field(default_factory=set)


def sanitise_filename(title: str, max_len: int = 120) -> str:
    cleaned = ILLEGAL_FILENAME_CHARS.sub("_", title).strip().rstrip(".")
    return cleaned[:max_len] or "untitled"


def _load_work_page(browser: Browser, work_url: str, title: str, work_id: int):
    """Returns a BeautifulSoup of the loaded work page, or None if the work is
    deleted/inaccessible (404)."""
    for attempt in range(1, MAX_WORK_ATTEMPTS + 1):
        soup, status = browser.goto(work_url)
        if soup is not None and status not in RETRYABLE_STATUSES:
            heading = soup.find("h2", {"class": "heading"}) or soup.find("h2")
            if heading is not None and "Error 404" in heading.get_text():
                return None
            return soup

        if attempt < MAX_WORK_ATTEMPTS:
            wait = backoff_seconds(attempt)
            log.warning(
                "Trouble loading '%s' (%s) (status=%s), attempt %d/%d, sleeping %ds...",
                title, work_id, status, attempt, MAX_WORK_ATTEMPTS, wait,
            )
            time.sleep(wait)
        else:
            raise RuntimeError(f"Could not load work {work_id} after {MAX_WORK_ATTEMPTS} attempts (status={status}).")
    return None


def _download_link_for_format(soup, fmt: str, work_url: str) -> str | None:
    download_li = soup.find("li", {"class": "download"})
    if download_li is None:
        return None
    for item in download_li.find_all("li"):
        a = item.find("a")
        if a and a.get_text(strip=True).upper() == fmt:
            return urljoin(work_url, a["href"])
    return None


def _fetch_format_bytes(browser: Browser, url: str, title: str, fmt: str) -> bytes | None:
    for attempt in range(1, MAX_WORK_ATTEMPTS + 1):
        try:
            return browser.fetch_bytes(url)
        except Exception as e:
            if attempt < MAX_WORK_ATTEMPTS:
                wait = backoff_seconds(attempt)
                log.warning(
                    "Trouble downloading '%s' as %s (%s), attempt %d/%d, sleeping %ds...",
                    title, fmt, e, attempt, MAX_WORK_ATTEMPTS, wait,
                )
                time.sleep(wait)
            else:
                log.error("Giving up on '%s' as %s: %s", title, fmt, e)
                return None
    return None


def _process_work(work, browser: Browser, config: Config, manifest: Manifest, summary: Summary, index: int):
    pending_formats = [
        fmt for fmt in config.formats if not manifest.has(work.id, fmt) 
        # get all formats that haven't been downloaded before
    ]
    if not pending_formats:
        log.info("[%d] '%s' (%s): already have all formats, skipping.", index, work.title, work.id)
        summary.already_had += 1
        return

    work_url = WORK_URL.format(id=work.id)
    title = sanitise_filename(work.title)

    log.info("[%d] Loading '%s' (%s)...", index, work.title, work.id)
    try:
        soup = _load_work_page(browser, work_url, work.title, work.id)
    except RuntimeError as e:
        log.error(str(e))
        summary.errored += 1
        return
    if soup is None:
        log.info("Skipping deleted/inaccessible work id %s", work.id)
        summary.skipped_deleted += 1
        return

    for fmt in [f for f in pending_formats if f != "HTML"]: # download all formats except html using ao3 given download feature
        ext = FORMAT_EXTENSIONS[fmt]
        out_dir = os.path.join(config.output_dir, fmt)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{title}_{work.id}.{ext}")

        link = _download_link_for_format(soup, fmt, work_url)
        if link is None:
            log.warning("Error occured when downloading '%s', skipping %s format.", work.title, fmt)
            summary.skipped_format += 1
            continue

        content = _fetch_format_bytes(browser, link, work.title, fmt)
        if content is None:
            log.warning("Error occured when downloading '%s', skipping %s format.", work.title, fmt)
            summary.errored += 1
            continue

        with open(out_path, "wb") as f:
            f.write(content)
        manifest.record(work.id, work.title, fmt)
        summary.downloaded += 1
        log.info("Saved %s", out_path)

    if "HTML" in pending_formats: # special case the full page save
        out_dir = os.path.join(config.output_dir, "HTML")
        os.makedirs(out_dir, exist_ok=True)
        html_path = os.path.join(out_dir, f"{title}_{work.id}.html")
        assets_dir = os.path.join(out_dir, f"{title}_{work.id}_files")
        try:
            browser.save_complete_page(work_url, html_path, assets_dir)
        except:
            log.error("Giving up on '%s' as HTML: %s", work.title, Exception)
            summary.errored += 1 # actual error here, since deletion was handled above
        else:
            manifest.record(work.id, work.title, "HTML")
            summary.downloaded += 1
            log.info("Saved %s", html_path)

    summary.processed_works.add(work.id)


def run(config: Config, browser: Browser) -> Summary:
    summary = Summary()
    browser.ensure_logged_in(config.username, config.password)
    manifest = Manifest(config.manifest_path)

    index = 0
    try:
        for kind, item in iter_bookmarked_works(browser, config.username, config.limit):
            if kind == "series":
                summary.skipped_series += 1
                continue

            index += 1
            _process_work(item, browser, config, manifest, summary, index)
    except RuntimeError as e:
        log.error(
            "%s Everything downloaded so far has been saved (%d file(s)); "
            "re-run the same command to pick up where this left off.",
            e, summary.downloaded,
        )
    except KeyboardInterrupt:
        log.warning("Interrupted by user. Progress so far has been saved; re-run to resume.")

    return summary
