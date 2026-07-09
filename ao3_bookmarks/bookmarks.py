import logging
import math
import re
import time
from dataclasses import dataclass

from .browser import RETRYABLE_STATUSES, Browser

log = logging.getLogger("ao3_bookmarks")

MAX_PAGE_ATTEMPTS = 5
BASE_BACKOFF_SECONDS = 30
MAX_BACKOFF_SECONDS = 300

BOOKMARKS_URL = "https://archiveofourown.org/users/{username}/bookmarks?page={page}"
WORKID_RE = re.compile(r"/works/(\d+)")

# Matches AO3's "1 - 20 of 1,333 Bookmarks by ..." index heading. Deliberately not
# based on the pagination widget's CSS classes/attributes, which have changed
# across AO3's pagination library versions before (e.g. dropping title="pagination")
# and silently produced a page count of 1, under-fetching the rest of the list.
_COUNT_HEADING_RE = re.compile(r"([\d,]+)\s*-\s*([\d,]+)\s+of\s+([\d,]+)")


@dataclass
class BookmarkedWork:
    id: int
    title: str


def backoff_seconds(attempt: int) -> int:
    return min(BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)), MAX_BACKOFF_SECONDS)


def _parse_page_count(soup) -> int:
    heading = soup.find("h2", {"class": "heading"}) or soup.find("h2")
    if heading is not None:
        match = _COUNT_HEADING_RE.search(heading.get_text())
        if match:
            start, end, total = (int(g.replace(",", "")) for g in match.groups())
            page_size = max(end - start + 1, 1)
            return max(math.ceil(total / page_size), 1)
    return 1


def _parse_bookmarks_page(soup):
    listing = soup.find("ol", {"class": "bookmark index group"})
    if listing is None:
        return None

    works = []
    series_count = 0
    for bookm in listing.find_all("li", {"class": ["bookmark", "index", "group"]}):
        if bookm.h4 is None:
            # no title link for deleted/inaccessible works.
            continue
        workid = None
        is_series = False
        workname = None
        for a in bookm.h4.find_all("a"):
            href = a.attrs.get("href", "")
            if href.startswith("/works"):
                workname = str(a.string)
                match = WORKID_RE.search(href)
                if match:
                    workid = int(match.group(1))
            elif href.startswith("/series"):
                is_series = True
        if workid is not None:
            works.append(BookmarkedWork(id=workid, title=workname))
        elif is_series:
            series_count += 1
    return works, series_count, _parse_page_count(soup)


def _fetch_page(browser: Browser, username: str, page: int):
    url = BOOKMARKS_URL.format(username=username, page=page)
    for attempt in range(1, MAX_PAGE_ATTEMPTS + 1):
        soup, status = browser.goto(url)

        if soup is not None and status not in RETRYABLE_STATUSES:
            parsed = _parse_bookmarks_page(soup)
            if parsed is not None:
                return parsed

        title = soup.find("title") if soup else None
        heading = soup.find("h2") if soup else None
        wait = backoff_seconds(attempt)
        log.warning(
            "Unexpected bookmarks page %d (status=%s, title=%r, heading=%r), attempt %d/%d, sleeping %ds...",
            page, status,
            title.text.strip() if title else None,
            heading.text.strip() if heading else None,
            attempt, MAX_PAGE_ATTEMPTS, wait,
        )
        time.sleep(wait)

    raise RuntimeError(
        f"Could not parse page {page} after {MAX_PAGE_ATTEMPTS} attempts."
    )


def iter_bookmarked_works(browser: Browser, username: str, limit: int | None = None):
    page = 1
    total_pages = None
    yielded = 0
    while total_pages is None or page <= total_pages:
        page_works, page_series, page_total_pages = _fetch_page(browser, username, page)
        if total_pages is None:
            total_pages = page_total_pages
            log.info("Bookmarks span %d page(s).", total_pages)

        log.info("Page %d/%d: %d work(s), %d series bookmark(s) on this page.",
                  page, total_pages, len(page_works), page_series)

        for work in page_works:
            yield "work", work
            yielded += 1
            if limit is not None and yielded >= limit:
                return
        for _ in range(page_series):
            yield "series", None

        page += 1
