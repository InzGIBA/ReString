"""Rewrite README.md into a PyPI-safe long description.

PyPI sanitizes the long description: <picture> and <source> tags are
stripped, SVG images are blocked, and relative paths do not resolve
outside GitHub. This script produces a description that renders there:

- the hero <picture> block becomes one <img> pointing at the committed
  social-preview PNG (absolute raw.githubusercontent URL);
- the feature-card <picture> blocks are dropped, the bullet list below
  carries the content;
- the demo photo and every relative link (docs/, examples/, LICENSE)
  become absolute github.com URLs;
- in-page anchors stay, PyPI generates its own heading slugs.

Usage: python3 scripts/build_pypi_readme.py [IN] [OUT]  (default in and
out: README.md). Idempotent: a second run on transformed content is a
no-op. The release workflow runs it on the build runners before
maturin, so the wheel and sdist metadata carry the PyPI-safe text while
the repository README keeps the GitHub-only rendering.
"""

import re
import sys

REPO = "https://github.com/InzGIBA/ReString"
RAW = "https://raw.githubusercontent.com/InzGIBA/ReString/main"

HERO_IMG = ('<img src="{raw}/assets/social-preview-light.png" '
            'alt="ReString: string art from a photo" width="100%">').format(raw=RAW)


def transform(text: str) -> str:
    def picture(match: re.Match) -> str:
        block = match.group(0)
        if "hero-dark.svg" in block:
            return HERO_IMG
        return ""  # feature cards: the bullet list below carries the content

    text = re.sub(r"<picture>.*?</picture>", picture, text, flags=re.DOTALL)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # the demo photo and any other repo image: absolute raw URL
    text = text.replace("](assets/", "]({}/assets/".format(RAW))

    # relative file links: absolute github blob URLs; anchors stay as they are
    text = re.sub(r"\]\((docs/[^)#]*)(#[^)]*)?\)",
                  lambda m: "]({repo}/blob/main/{path}{anchor})".format(
                      repo=REPO, path=m.group(1), anchor=m.group(2) or ""), text)
    text = re.sub(r"\]\((examples/[^)#]*)(#[^)]*)?\)",
                  lambda m: "]({repo}/blob/main/{path}{anchor})".format(
                      repo=REPO, path=m.group(1), anchor=m.group(2) or ""), text)
    text = text.replace("](LICENSE)", "]({}/blob/main/LICENSE)".format(REPO))
    return text


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "README.md"
    dst = sys.argv[2] if len(sys.argv) > 2 else src
    result = transform(open(src, encoding="utf-8").read())
    open(dst, "w", encoding="utf-8").write(result)
    leftovers = re.findall(r"<picture>|\]\(assets/|\]\(docs/|\]\(examples/", result)
    if leftovers:
        print("PyPI-unsafe fragments remain: {}".format(sorted(set(leftovers))))
        sys.exit(1)
    print("wrote {} ({} bytes)".format(dst, len(result)))


if __name__ == "__main__":
    main()
