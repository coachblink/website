# blink-brain/website

Marketing landing page for [Blink](https://github.com/blink-brain/blink), an AI executive function partner for people with ADHD.

Plain static HTML/CSS, no build step. Served via GitHub Pages at https://blink-brain.github.io/website/.

## Local preview

```
python3 -m http.server 8000
```

Then open http://localhost:8000.

## Validating the site

Run the site validator before merging any change that adds, removes, or
renames a page. It checks that every page has a title and meta description,
that `sitemap.xml` matches the pages on disk, that `robots.txt` points at the
sitemap, that `llms.txt` links to `pricing.md`, and that internal links
resolve.

```
python3 scripts/validate.py
```

To check the validator's own logic (it must pass a healthy fixture and
reject a broken one):

```
python3 scripts/validate.py --self-test
```

## Updating brand assets

Source SVGs/PNGs live in `assets/` and are copied from the main [`blink`](https://github.com/blink-brain/blink) repo's `assets/branding/` directory. Keep them in sync if the brand kit changes there.
