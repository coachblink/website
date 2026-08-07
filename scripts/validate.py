#!/usr/bin/env python3
"""AEO/site-health validator for the coachblink.com static site.

Checks that every crawlable page has a title and meta description, that
sitemap.xml is valid XML covering exactly the crawlable pages on disk (and
nothing else), that robots.txt points at the sitemap, that llms.txt links to
pricing.md, and that every internal relative link resolves to a real file.

Run before merging any change that adds, removes, or renames a page:
    python3 scripts/validate.py

Self-test (checks that the validator itself catches real breakage):
    python3 scripts/validate.py --self-test
"""

import argparse
import pathlib
import re
import sys
import tempfile
import xml.etree.ElementTree as ET

SITE_BASE = "https://coachblink.com"
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

# go/ holds JS redirect stubs for outbound share links, not indexable content.
EXCLUDED_DIRS = {".git", "go", "assets", ".kazi"}


def crawlable_html_files(root: pathlib.Path):
    files = []
    for path in sorted(root.rglob("*.html")):
        rel = path.relative_to(root)
        if rel.parts[0] in EXCLUDED_DIRS:
            continue
        files.append(path)
    return files


def url_for(root: pathlib.Path, path: pathlib.Path) -> str:
    rel = path.relative_to(root).as_posix()
    if rel == "index.html":
        return SITE_BASE + "/"
    if rel.endswith("/index.html"):
        return SITE_BASE + "/" + rel[: -len("index.html")]
    return SITE_BASE + "/" + rel


def check_meta(root, errors):
    for path in crawlable_html_files(root):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(root)
        if not re.search(r"<title>[^<]+</title>", text):
            errors.append(f"{rel}: missing or empty <title>")
        if not re.search(r'name="description"\s+content="[^"]+"', text):
            errors.append(f"{rel}: missing or empty meta description")


def check_sitemap(root, errors):
    sitemap_path = root / "sitemap.xml"
    if not sitemap_path.exists():
        errors.append("sitemap.xml is missing")
        return

    try:
        tree = ET.parse(sitemap_path)
    except ET.ParseError as exc:
        errors.append(f"sitemap.xml is not valid XML: {exc}")
        return

    locs = {
        loc.text.strip()
        for loc in tree.getroot().findall(".//sm:loc", SITEMAP_NS)
        if loc.text
    }

    expected = {url_for(root, path) for path in crawlable_html_files(root)}
    if (root / "pricing.md").exists():
        expected.add(SITE_BASE + "/pricing.md")

    for url in sorted(expected - locs):
        errors.append(f"sitemap.xml is missing an entry for {url}")
    for url in sorted(locs - expected):
        errors.append(f"sitemap.xml references {url}, which does not exist on disk")


def check_robots(root, errors):
    robots_path = root / "robots.txt"
    if not robots_path.exists():
        errors.append("robots.txt is missing")
        return
    if "sitemap.xml" not in robots_path.read_text(encoding="utf-8").lower():
        errors.append("robots.txt does not reference sitemap.xml")


def check_llms_txt(root, errors):
    llms_path = root / "llms.txt"
    if not llms_path.exists():
        errors.append("llms.txt is missing")
        return
    if "pricing.md" not in llms_path.read_text(encoding="utf-8"):
        errors.append("llms.txt does not link to pricing.md")


def check_internal_links(root, errors):
    root = root.resolve()
    for path in crawlable_html_files(root):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(root)
        for href in re.findall(r'href="([^"#][^"]*)"', text):
            if href.startswith(("http://", "https://", "mailto:", "tel:")):
                continue
            target = (path.parent / href.split("?")[0].split("#")[0]).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                errors.append(f"{rel}: link {href!r} escapes the site root")
                continue
            if not target.exists():
                errors.append(f"{rel}: broken internal link {href!r}")


CHECKS = (check_meta, check_sitemap, check_robots, check_llms_txt, check_internal_links)


def run_checks(root: pathlib.Path):
    errors = []
    for check in CHECKS:
        check(root, errors)
    return errors


def _sitemap_xml(urls):
    body = "".join(f"<url><loc>{url}</loc></url>" for url in urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>\n'
    )


def _write_fixture(root: pathlib.Path):
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.html").write_text(
        "<!doctype html><html><head><title>Fixture</title>"
        '<meta name="description" content="A fixture site.">'
        '</head><body><a href="about.html">About</a></body></html>',
        encoding="utf-8",
    )
    (root / "about.html").write_text(
        "<!doctype html><html><head><title>About</title>"
        '<meta name="description" content="About the fixture.">'
        "</head><body>About</body></html>",
        encoding="utf-8",
    )
    (root / "pricing.md").write_text("# Pricing\n", encoding="utf-8")
    (root / "sitemap.xml").write_text(
        _sitemap_xml(
            [SITE_BASE + "/", SITE_BASE + "/about.html", SITE_BASE + "/pricing.md"]
        ),
        encoding="utf-8",
    )
    (root / "robots.txt").write_text(
        f"Sitemap: {SITE_BASE}/sitemap.xml\n", encoding="utf-8"
    )
    (root / "llms.txt").write_text("See pricing.md for pricing.\n", encoding="utf-8")


def self_test() -> bool:
    """Two-sided: the validator must pass a healthy fixture and must reject
    a broken one (missing sitemap entry + dangling internal link)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)

        good = tmp_path / "good"
        _write_fixture(good)
        good_errors = run_checks(good)
        if good_errors:
            print("self-test FAILED: validator rejected a healthy site fixture:")
            for error in good_errors:
                print(f"  - {error}")
            return False

        bad = tmp_path / "bad"
        _write_fixture(bad)
        (bad / "sitemap.xml").write_text(
            _sitemap_xml([SITE_BASE + "/"]), encoding="utf-8"
        )
        (bad / "index.html").write_text(
            (bad / "index.html")
            .read_text(encoding="utf-8")
            .replace('href="about.html"', 'href="missing.html"'),
            encoding="utf-8",
        )
        bad_errors = run_checks(bad)
        if not bad_errors:
            print("self-test FAILED: validator accepted a broken site fixture")
            return False

    print("self-test OK: validator passes a healthy fixture and rejects a broken one")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the validator's own two-sided self-test instead of validating this repo",
    )
    args = parser.parse_args()

    if args.self_test:
        sys.exit(0 if self_test() else 1)

    root = pathlib.Path(__file__).resolve().parent.parent
    errors = run_checks(root)
    if errors:
        print(f"{len(errors)} problem(s) found:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)

    print("OK: site validation passed")
    sys.exit(0)


if __name__ == "__main__":
    main()
