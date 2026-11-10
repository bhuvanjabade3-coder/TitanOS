"""Browser integration: open/search in the user's browser, read pages for the
assistant, bookmarks, and permissioned downloads. TITAN never stores website
passwords and does not automate logins."""
from __future__ import annotations

import ipaddress
import re
import socket
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse

import httpx

from ..core import ActionError, Ctx, Gate
from ..db import now
from ..security.risk import Risk
from ._tools import need, spawn
from .terminal import clean_env

ENGINES = {"duckduckgo": "https://duckduckgo.com/?q={}", "google": "https://www.google.com/search?q={}",
           "bing": "https://www.bing.com/search?q={}"}
MAX_PAGE = 2_000_000
UA = "TITAN-OS/0.1 (desktop assistant)"


def check_url(url: str, public_only: bool = True) -> str:
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:(?!\d+(/|$))", url) and "://" not in url:
        raise ActionError(f"{url}: only http(s) URLs are supported")  # javascript:, data:, mailto: …
    try:
        u = urlparse(url if "://" in url else "https://" + url)
        port = u.port
    except ValueError:
        raise ActionError(f"{url}: not a valid URL")
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ActionError(f"{url}: only http(s) URLs are supported")
    if u.username or u.password:
        raise ActionError("URLs with embedded credentials are not allowed")
    if public_only:
        try:
            infos = socket.getaddrinfo(u.hostname, port or 443, proto=socket.IPPROTO_TCP)
        except socket.gaierror:
            raise ActionError(f"{u.hostname}: could not be resolved")
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                raise ActionError(f"{u.hostname} resolves to a local/private address; TITAN only fetches public sites")
    return u.geturl()


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template", "head"}
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "pre", "blockquote"}

    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base, self.title, self.parts, self.links = base, "", [], []
        self._skip, self._in_title, self._href = 0, False, None

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP and tag != "head":
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "a":
            self._href = dict(attrs).get("href")
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and tag != "head":
            self._skip = max(0, self._skip - 1)
        elif tag == "title":
            self._in_title = False
        elif tag == "a":
            self._href = None

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)
            if self._href and data.strip() and len(self.links) < 100:
                href = urljoin(self.base, self._href)
                if href.startswith("http"):
                    self.links.append({"text": data.strip()[:120], "url": href})


def extract(html: str, base: str) -> dict:
    p = _Text(base)
    p.feed(html)
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(p.parts))
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return {"title": p.title.strip(), "text": text, "links": p.links}


def b_open(ctx: Ctx, a: dict) -> dict:
    url = check_url(a["url"], public_only=False)
    need("xdg-open")
    spawn(["xdg-open", url], env=clean_env())
    return {"opened": url}


def b_search(ctx: Ctx, a: dict) -> dict:
    engine = ctx.db.pref("browser.search_engine", "duckduckgo")
    url = ENGINES.get(engine, ENGINES["duckduckgo"]).format(quote_plus(a["query"]))
    need("xdg-open")
    spawn(["xdg-open", url], env=clean_env())
    return {"opened": url, "engine": engine}


def b_fetch(ctx: Ctx, a: dict) -> dict:
    url = check_url(a["url"])
    limit = min(int(a.get("max_chars", 20_000)), 200_000)
    try:
        with httpx.Client(follow_redirects=False, timeout=20, headers={"User-Agent": UA}) as c:
            for _ in range(6):  # re-validate every hop so redirects cannot reach private hosts
                r = c.get(url)
                if r.is_redirect:
                    url = check_url(urljoin(url, r.headers.get("location", "")))
                    continue
                break
            else:
                raise ActionError("too many redirects")
    except httpx.HTTPError as e:
        raise ActionError(f"could not fetch {url}: {e}")
    if r.status_code in (401, 403):
        raise ActionError(f"{url} requires sign-in or denies automated access (HTTP {r.status_code}); TITAN does not bypass that")
    if r.status_code >= 400:
        raise ActionError(f"{url} returned HTTP {r.status_code}")
    ctype = r.headers.get("content-type", "")
    if "html" in ctype:
        doc = extract(r.text[:MAX_PAGE], url)
    elif ctype.startswith("text/") or "json" in ctype:
        doc = {"title": "", "text": r.text[:MAX_PAGE], "links": []}
    else:
        raise ActionError(f"{url} is {ctype or 'an unknown type'}, not a readable page")
    return {"url": url, "title": doc["title"], "text": doc["text"][:limit],
            "truncated": len(doc["text"]) > limit, "links": doc["links"][:40]}


def g_download(ctx: Ctx, a: dict) -> Gate:
    url = check_url(a["url"])
    return Gate(Risk.MEDIUM, ["downloads a file from the internet into ~/Downloads"], f"Download {url}")


def b_download(ctx: Ctx, a: dict) -> dict:
    url = check_url(a["url"])
    ddir = ctx.settings.home / "Downloads"
    ddir.mkdir(exist_ok=True)
    name = re.sub(r"[^\w.\-]+", "_", a.get("filename") or Path(urlparse(url).path).name or "download")[:120] or "download"
    target, i = ddir / name, 1
    while target.exists():
        target, i = ddir / f"{Path(name).stem} ({i}){Path(name).suffix}", i + 1
    part = target.with_name(target.name + ".part")

    def job(ctl):
        try:
            with httpx.stream("GET", url, follow_redirects=False, timeout=30, headers={"User-Agent": UA}) as r:
                if r.status_code != 200:
                    raise RuntimeError(f"HTTP {r.status_code} (redirects are not followed for downloads)")
                total, got = int(r.headers.get("content-length") or 0), 0
                with open(part, "wb") as f:
                    for chunk in r.iter_bytes(65536):
                        ctl.check()
                        f.write(chunk)
                        got += len(chunk)
                        ctl.progress(got / total if total else 0.0, f"{got} bytes")
            part.rename(target)
        except BaseException as e:
            part.unlink(missing_ok=True)
            if not ctl.cancelled:
                ctx.core.notifier.notify("download", "Download failed", f"{url}: {e}", "warning")
            raise
        ctx.core.notifier.notify("download", "Download complete", str(target))
        return {"path": str(target), "bytes": got}

    task = ctx.core.tasks.submit(f"Download {name}", job, locks=[target])
    return {"task_id": task["id"], "target": str(target)}


def bm_add(ctx: Ctx, a: dict) -> dict:
    url = check_url(a["url"], public_only=False)
    bid = ctx.db.x("INSERT INTO bookmarks(title, url, created_at) VALUES(?,?,?)", (a.get("title") or url, url, now()))
    return {"id": bid, "url": url}


def register(reg) -> None:
    S, I = {"type": "string"}, {"type": "integer"}
    reg.add("browser.open", "browser", "Open a URL in the user's default browser", b_open, {"url": S}, ["url"])
    reg.add("browser.search", "browser", "Open a web search for a query in the user's default browser", b_search, {"query": S}, ["query"])
    reg.add("browser.fetch", "browser", "Fetch a public web page and return its readable text and links (to summarise or extract information)",
            b_fetch, {"url": S, "max_chars": I}, ["url"], readonly=True)
    reg.add("browser.download", "browser", "Download a file into ~/Downloads as a background task (asks the user first)",
            b_download, {"url": S, "filename": S}, ["url"], gate=g_download)
    reg.add("bookmarks.add", "browser", "Save a bookmark", bm_add, {"url": S, "title": S}, ["url"])
    reg.add("bookmarks.list", "browser", "List saved bookmarks",
            lambda c, a: c.db.q("SELECT * FROM bookmarks ORDER BY id DESC"), readonly=True)
    reg.add("bookmarks.delete", "browser", "Delete a bookmark by id",
            lambda c, a: {"deleted": c.db.x("DELETE FROM bookmarks WHERE id=?", (a["id"],))}, {"id": I}, ["id"])
