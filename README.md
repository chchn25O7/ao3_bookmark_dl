# ao3 Bookmark Downloader

disrespecting the wishes of online people has never been easier!\
download your ao3 bookmarks and protect yourself against deleted fics

## Setup

```
python -m venv .venv
.venv\Scripts\activate 
pip install -r requirements.txt
playwright install chromium
```

Make a file called `.env` and fill in your ao3 credentials as such:

```
AO3_USERNAME=your_username
AO3_PASSWORD=your_password
```

## Usage

Run the setup, then run this command.

```
python -m ao3_bookmarks [options go here]
```

Files are saved under `downloads/<FORMAT>/<title>_<work_id>.<ext>` by default. History is updated as the downloads happen, you can ctrl-c to break at any time. 

**The HTML option is different from ao3's inbuilt Download -> HTML**

`--formats HTML` instead captures the work in the same way a browser's "Save As -> Webpage, Complete" would, saving to `downloads/HTML/<title>_<id>.html`
with a `downloads/HTML/<title>_<id>_files/` folder with the images/CSS/fonts it uses. 

This means that custom HTML and workskins should look similar to how they're intended to look.

### Options

| Flag | Default | Description |
|---|---|---|
| `--formats` | `PDF` | Comma-separated: `PDF,EPUB,MOBI,AZW3,HTML` |
| `--output-dir` | `downloads` | Where files are saved |
| `--manifest` | `manifest.json` | Which file is used as history |
| `--delay` | `5.0` | Seconds to wait between requests (any page load or file download) |
| `--limit N` | none | Only try download the first N bookmarks |
| `--force` | off | Ignore history, re-download everything |
| `--profile-dir` | `.pw-profile` | Persistent browser profile dir (keeps you logged in between runs) |
| `-v/--verbose` | off | Debug logging |

## Notes

- You may be rate limited, increase the delay between requests if this happens (or try again later)
- This won't redownload fics that have been updated since your last download. You need to use `--force` flag to redownload all (sorry)
