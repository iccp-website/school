#!/usr/bin/env python3
"""Consistency checks for the summer school site (standard library only).

Checks index.html together with every pages/*.html fragment:
  * tags are balanced (every non-void element is closed, in order);
  * ids are unique across the shell plus each page, and no id equals a page
    name (the browser would jump to it natively on #page);
  * every internal link #page or #page/anchor points to an existing page and,
    if given, an existing id on that page;
  * every local file referenced by src, srcset, href, data-src or a CSS
    url(...) exists, with exactly the same capitalization;
  * every <img> with a src has alt, width and height attributes;
  * gallery JPEGs carry no metadata (EXIF/GPS, XMP, ICC, IPTC), and each one
    is used by some page (stale photos would only bloat the repository).

Usage (from the repository root):
  python3 tools/check_site.py             # local checks
  python3 tools/check_site.py --external  # also fetch every external link
Exits with status 1 if any problem is found.
"""
import argparse
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class Page(HTMLParser):
    def __init__(self, path: Path):
        super().__init__(convert_charrefs=True)
        self.path = path
        self.stack = []
        self.ids = {}
        self.refs = []      # (attr, value, line)
        self.imgs = []      # (attrs, line)
        self.problems = []
        self.feed(path.read_text(encoding="utf-8"))
        self.close()
        for tag, line in self.stack:
            self.problems.append(f"{self.rel()}:{line}: <{tag}> is never closed")

    def rel(self):
        return self.path.relative_to(REPO).as_posix()

    def handle_starttag(self, tag, attrs):
        line = self.getpos()[0]
        a = dict(attrs)
        if tag not in VOID:
            self.stack.append((tag, line))
        if "id" in a:
            if a["id"] in self.ids:
                self.problems.append(f"{self.rel()}:{line}: duplicate id '{a['id']}' (first at line {self.ids[a['id']]})")
            self.ids.setdefault(a["id"], line)
        for attr in ("src", "href", "data-src"):
            if a.get(attr) is not None:
                self.refs.append((attr, a[attr], line))
        for candidate in (a.get("srcset") or "").split(","):
            if candidate.strip():
                self.refs.append(("srcset", candidate.split()[0], line))
        for url in re.findall(r"url\(['\"]?([^'\")]+)['\"]?\)", a.get("style") or ""):
            self.refs.append(("style", url, line))
        if tag == "img":
            self.imgs.append((a, line))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.stack and self.stack[-1][0] == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        line = self.getpos()[0]
        if tag in VOID:
            return
        if not self.stack:
            self.problems.append(f"{self.rel()}:{line}: stray </{tag}>")
            return
        if self.stack[-1][0] == tag:
            self.stack.pop()
            return
        open_tags = [t for t, _ in self.stack]
        if tag in open_tags:
            while self.stack and self.stack[-1][0] != tag:
                t, l = self.stack.pop()
                self.problems.append(f"{self.rel()}:{l}: <{t}> is not closed before </{tag}> at line {line}")
            self.stack.pop()
        else:
            self.problems.append(f"{self.rel()}:{line}: stray </{tag}>")


def exists_exact_case(rel_path: str) -> bool:
    """True if rel_path exists under REPO with exactly this capitalization."""
    current = REPO
    for part in Path(rel_path).parts:
        if part in (".", ""):
            continue
        if not current.is_dir() or part not in os.listdir(current):
            return False
        current = current / part
    return True


def jpeg_metadata(path: Path):
    """Return the names of metadata segments found in a JPEG file."""
    data = path.read_bytes()
    found = []
    i = 2
    while i + 4 <= len(data) and data[i] == 0xFF:
        marker = data[i + 1]
        if marker == 0xDA:  # start of scan: no more headers
            break
        length = int.from_bytes(data[i + 2:i + 4], "big")
        body = data[i + 4:i + 2 + length]
        if marker == 0xE1 and body.startswith(b"Exif"):
            found.append("EXIF")
        elif marker == 0xE1 and body.startswith(b"http://ns.adobe.com/xap"):
            found.append("XMP")
        elif marker == 0xE2 and body.startswith(b"ICC_PROFILE"):
            found.append("ICC")
        elif marker == 0xED:
            found.append("IPTC")
        i += 2 + length
    return found


def fetch_status(url, context=None):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (site link check)"})
    try:
        with urllib.request.urlopen(req, timeout=20, context=context) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def check_external(urls):
    """Return (problems, warnings) for the given external URLs."""
    problems, warnings = [], []
    for url in sorted(urls):
        try:
            status = fetch_status(url)
        except urllib.error.URLError as e:
            if not isinstance(e.reason, ssl.SSLCertVerificationError):
                problems.append(f"external: {url}: {e}")
                continue
            # Servers that omit their intermediate certificate fail strict clients
            # like this one but still work in browsers; retry without verification.
            try:
                status = fetch_status(url, context=ssl._create_unverified_context())
            except Exception as e2:
                problems.append(f"external: {url}: {e2}")
                continue
            warnings.append(f"external: {url}: certificate chain incomplete (browsers usually accept it)")
        except Exception as e:  # timeouts and other network errors
            problems.append(f"external: {url}: {e}")
            continue
        if status >= 400:
            problems.append(f"external: {url}: HTTP {status}")
    return problems, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--external", action="store_true", help="also fetch every external http(s) link")
    args = ap.parse_args()

    shell = Page(REPO / "index.html")
    pages = {p.stem: Page(p) for p in sorted((REPO / "pages").glob("*.html"))}
    problems = list(shell.problems)
    external = set()

    for name, page in pages.items():
        problems += page.problems
        for dup in sorted(set(page.ids) & set(shell.ids)):
            problems.append(f"{page.rel()}:{page.ids[dup]}: id '{dup}' also used in index.html")
        for pid in sorted(set(page.ids) & set(pages)):
            problems.append(f"{page.rel()}:{page.ids[pid]}: id '{pid}' equals a page name")
    for pid in sorted(set(shell.ids) & set(pages)):
        problems.append(f"index.html:{shell.ids[pid]}: id '{pid}' equals a page name")

    for doc in [shell, *pages.values()]:
        for attr, value, line in doc.refs:
            where = f"{doc.rel()}:{line}"
            if value.startswith(("http://", "https://")):
                external.add(value)
            elif value.startswith("#"):
                target, _, anchor = value[1:].partition("/")
                target = target or "home"
                if target not in pages:
                    problems.append(f"{where}: link {value} points to missing page pages/{target}.html")
                elif anchor and anchor not in pages[target].ids:
                    problems.append(f"{where}: link {value} points to missing id '{anchor}' in pages/{target}.html")
            elif value.startswith(("mailto:", "tel:", "data:")) or value == "":
                continue
            else:
                path = value.split("#")[0].split("?")[0]
                if path and not exists_exact_case(path):
                    problems.append(f"{where}: {attr}='{value}' does not exist (check capitalization)")
        for a, line in doc.imgs:
            if not a.get("src"):
                continue
            missing = [k for k in ("alt", "width", "height") if a.get(k) is None]
            if missing:
                problems.append(f"{doc.rel()}:{line}: <img src='{a['src']}'> lacks {', '.join(missing)}")

    referenced = {os.path.normpath(value.split("#")[0].split("?")[0])
                  for doc in [shell, *pages.values()] for _, value, _ in doc.refs
                  if not value.startswith(("http://", "https://", "#", "mailto:", "tel:", "data:"))}
    for jpg in sorted((REPO / "static" / "img" / "gallery").rglob("*.jpg")):
        rel = jpg.relative_to(REPO).as_posix()
        meta = jpeg_metadata(jpg)
        if meta:
            problems.append(f"{rel}: contains {', '.join(meta)} metadata")
        if os.path.normpath(rel) not in referenced:
            problems.append(f"{rel}: not used by any page (delete it to keep the repository small)")

    warnings = []
    if args.external:
        ext_problems, warnings = check_external(external)
        problems += ext_problems

    for w in warnings:
        print("warning:", w)
    for p in problems:
        print(p)
    n_pages = len(pages)
    print(f"{'FAILED' if problems else 'OK'}: {len(problems)} problem(s); checked index.html and {n_pages} page(s)"
          + (f", {len(external)} external link(s)" if args.external else ""))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
