import hashlib
import logging
import os
import random
import re
import time
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

log = logging.getLogger("ao3_bookmarks")

NAV_TIMEOUT_MS = 45_000
RETRYABLE_STATUSES = {429, 503}
ASSET_RESOURCE_TYPES = {"image", "stylesheet", "font"}
ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
CSS_URL_RE = re.compile(r'url\(\s*[\'"]?([^\'")]+)[\'"]?\s*\)')


def _safe_asset_filename(url: str) -> str:
    base = os.path.basename(urlparse(url).path) or "asset"
    base = ILLEGAL_FILENAME_CHARS.sub("_", base)
    root, ext = os.path.splitext(base)
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return f"{root}_{digest}{ext or '.bin'}"


class Browser:
    def __init__(self, profile_dir: str, delay: float = 5.0):
        self._playwright = sync_playwright().start()
        self.context = self._playwright.chromium.launch_persistent_context(
            profile_dir, headless=False
        )
        self.context.set_default_navigation_timeout(NAV_TIMEOUT_MS)
        self.page = self.context.new_page()
        self.delay = delay
        log.debug("Browser loaded successfully.")

    def close(self):
        self.context.close()
        self._playwright.stop()

    def _cooldown(self):
        if self.delay <= 0: # user is stupid, pretend its 0
            return
        time.sleep(self.delay + random.uniform(0, self.delay * 0.25))

    def ensure_logged_in(self, username: str, password: str):
        self.page.goto("https://archiveofourown.org/users/login", wait_until="load")

        if self.page.locator('input[name="user[login]"]').count() > 0:
            log.info("Logging in as %s...", username)
            self.page.fill("#user_login", username)
            self.page.fill("#user_password", password)
            self.page.press("#user_password", "Enter")
            self.page.wait_for_load_state("load")
            if self.page.locator('input[name="user[login]"]').count() > 0:
                raise SystemExit("Login failed: still on the login page after submitting credentials.")
            log.info("Logged in successfully.")
            return

        # might already be logged in 
        title = self.page.title()
        if self.page.url.rstrip("/").endswith("/users/login"):
            raise SystemExit(
                f"Could not load the login form (title: {title!r}, url: {self.page.url})."
            )
        log.info("Already logged in.")

    def goto(self, url: str):
        """Navigates to url. Returns (soup, status); status is None on a hard
        navigation failure (timeout, DNS error, etc.) rather than an HTTP error."""
        self._cooldown()
        try:
            response = self.page.goto(url, wait_until="load")
        except:
            log.warning("Navigation error for %s: %s", url, PlaywrightError)
            return None, None
        soup = BeautifulSoup(self.page.content(), "lxml")
        return soup, (response.status if response else None)

    def fetch_bytes(self, url: str) -> bytes:
        self._cooldown()
        response = self.context.request.get(url)
        return response.body()

    def save_complete_page(self, url: str, html_path: str, assets_dir: str):
        """Saves the fully-rendered page at url as a self-contained bundle: html_path
        plus assets_dir populated with localized images/stylesheets/fonts, similar to
        a browser's 'Webpage, Complete' save."""
        self._cooldown()
        captured = {}  # absolute resource url -> bytes

        def on_response(response):
            try:
                if response.request.resource_type in ASSET_RESOURCE_TYPES and response.ok:
                    captured[response.url] = response.body()
            except PlaywrightError:
                pass  # error happened, just skip

        self.page.on("response", on_response)
        try:
            self.page.goto(url, wait_until="networkidle")
        finally:
            self.page.remove_listener("response", on_response)

        soup = BeautifulSoup(self.page.content(), "lxml")
        os.makedirs(assets_dir, exist_ok=True)
        assets_dirname = os.path.basename(assets_dir.rstrip("/\\"))
        url_to_local = {}

        def localize(base_url: str, ref: str):
            absolute = urljoin(base_url, ref)
            if absolute not in captured:
                return None
            if absolute not in url_to_local:
                filename = _safe_asset_filename(absolute)
                with open(os.path.join(assets_dir, filename), "wb") as f:
                    f.write(captured[absolute])
                url_to_local[absolute] = filename
            return url_to_local[absolute]

        css_files = []  # (local_path, original_absolute_url)
        for img in soup.find_all("img", src=True):
            local = localize(url, img["src"])
            if local:
                img["src"] = f"{assets_dirname}/{local}"
        for link in soup.find_all("link", href=True):
            rel = link.get("rel") or []
            if "stylesheet" not in rel:
                continue
            css_url = urljoin(url, link["href"])
            local = localize(url, link["href"])
            if local:
                css_files.append((os.path.join(assets_dir, local), css_url))
                link["href"] = f"{assets_dirname}/{local}"

        for css_path, css_url in css_files:
            with open(css_path, "r", encoding="utf-8", errors="ignore") as f:
                css_text = f.read()

            def replace_css_url(match, css_url=css_url):
                local = localize(css_url, match.group(1))
                return f'url("{local}")' if local else match.group(0)

            new_css_text = CSS_URL_RE.sub(replace_css_url, css_text)
            if new_css_text != css_text:
                with open(css_path, "w", encoding="utf-8") as f:
                    f.write(new_css_text)

        os.makedirs(os.path.dirname(html_path) or ".", exist_ok=True)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(str(soup))
