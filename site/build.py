"""Build the English and Chinese pages of rtloop.com from one bilingual source.

src/index.html carries every visible string twice, in <span class="en"> and
<span class="zh">, plus {{PLACEHOLDERS}} for per-page head content. This script
writes public/index.html (English) and public/zh/index.html (Traditional
Chinese) with the other language removed, so crawlers and text extractors read
one clean language per page.

Usage: python site/build.py
"""

import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src" / "index.html"
OUT = ROOT / "public"
SITE = "https://rtloop.com"

PAGES = {
    "en": {
        "file": OUT / "index.html",
        "lang": "en",
        "url": f"{SITE}/",
        "title": "RTLoop — Bring AI into IC design. Let the tools be the judge.",
        "description": (
            "RTLoop helps IC design teams adopt AI. Low-cost models write RTL one module at a time; "
            "simulation, structural checks and synthesis decide what passes. AI adoption consulting "
            "and verified RTL projects, founded in Taiwan in 2026."
        ),
        "og_locale": "en_US",
    },
    "zh": {
        "file": OUT / "zh" / "index.html",
        "lang": "zh-Hant",
        "url": f"{SITE}/zh/",
        "title": "RTLoop｜把 AI 帶進 IC 設計，讓工具當裁判",
        "description": (
            "RTLoop 協助 IC 設計團隊導入 AI：低成本模型一次只寫一個模組，由模擬、結構檢查與合成決定能不能通過。"
            "提供 IC 設計 AI 導入顧問與附完整證據的 RTL 專案，2026 年於台灣成立。"
        ),
        "og_locale": "zh_TW",
    },
}


class LangFilter(HTMLParser):
    """Copy the document verbatim, dropping every <span> subtree tagged with `drop`."""

    def __init__(self, drop):
        super().__init__(convert_charrefs=False)
        self.drop = drop
        self.out = []
        self.depth = 0  # <span> nesting depth inside the subtree being dropped
        self.dropped = 0

    def handle_starttag(self, tag, attrs):
        if self.depth:
            if tag == "span":
                self.depth += 1
            return
        classes = dict(attrs).get("class") or ""
        if self.drop in classes.split():
            if tag != "span":
                raise ValueError(f"language class on <{tag}>; only <span> is supported")
            self.depth = 1
            self.dropped += 1
            return
        self.out.append(self.get_starttag_text())

    def handle_startendtag(self, tag, attrs):
        if not self.depth:
            self.out.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if self.depth:
            if tag == "span":
                self.depth -= 1
            return
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.depth:
            self.out.append(data)

    def handle_entityref(self, name):
        if not self.depth:
            self.out.append(f"&{name};")

    def handle_charref(self, name):
        if not self.depth:
            self.out.append(f"&#{name};")

    def handle_comment(self, data):
        if not self.depth:
            self.out.append(f"<!--{data}-->")

    def handle_decl(self, decl):
        self.out.append(f"<!{decl}>")


def head_links(code):
    page = PAGES[code]
    other = "zh" if code == "en" else "en"
    lines = [
        f'<link rel="canonical" href="{page["url"]}">',
        f'<link rel="alternate" hreflang="en" href="{PAGES["en"]["url"]}">',
        f'<link rel="alternate" hreflang="zh-Hant" href="{PAGES["zh"]["url"]}">',
        f'<link rel="alternate" hreflang="x-default" href="{PAGES["en"]["url"]}">',
        f'<meta property="og:url" content="{page["url"]}">',
        f'<meta property="og:locale" content="{page["og_locale"]}">',
        f'<meta property="og:locale:alternate" content="{PAGES[other]["og_locale"]}">',
    ]
    return "\n".join(lines)


FONT_LATIN = "family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500"
FONT_TC = "family=Noto+Sans+TC:wght@400;500;700"


def fonts(code):
    # The English page skips the Chinese font; its few CJK labels fall back to system fonts.
    families = FONT_LATIN if code == "en" else f"{FONT_LATIN}&{FONT_TC}"
    return f'<link href="https://fonts.googleapis.com/css2?{families}&display=swap" rel="stylesheet">'


def head_script(code):
    script = "var r=document.documentElement;r.classList.add('js');"
    if code == "en":
        # First visit from a Chinese-language browser goes to the Chinese page,
        # unless the reader has already picked a language with the switch.
        script += (
            "var p=null;try{p=localStorage.getItem('rtloop-lang')}catch(e){}"
            "if(!p&&(navigator.language||'').toLowerCase().indexOf('zh')===0)"
            "{location.replace('/zh/'+location.hash)}"
        )
    return "(function(){" + script + "})();"


def lang_switch(code):
    def link(target, label):
        current = ' aria-current="page"' if target == code else ""
        href = "/" if target == "en" else "/zh/"
        hreflang = PAGES[target]["lang"]
        return f'<a href="{href}" hreflang="{hreflang}" data-lang-link="{target}"{current}>{label}</a>'

    return link("en", "EN") + link("zh", "中文")


def build(code):
    page = PAGES[code]
    source = SRC.read_text(encoding="utf-8")
    parser = LangFilter("zh" if code == "en" else "en")
    parser.feed(source)
    parser.close()
    if parser.depth:
        raise ValueError("unbalanced <span> in source")
    html = "".join(parser.out)

    replacements = {
        "{{LANG}}": page["lang"],
        "{{CODE}}": code,
        "{{TITLE}}": page["title"],
        "{{DESCRIPTION}}": page["description"],
        "{{HEAD_LINKS}}": head_links(code),
        "{{FONTS}}": fonts(code),
        "{{HEAD_SCRIPT}}": head_script(code),
        "{{LANG_SWITCH}}": lang_switch(code),
    }
    for key, value in replacements.items():
        if key not in html:
            raise ValueError(f"placeholder {key} missing from source")
        html = html.replace(key, value)
    # Attribute text that can't hold <span>s is written {{i18n:English|中文}}.
    html = re.sub(r"\{\{i18n:([^|{}]*)\|([^{}]*)\}\}", lambda m: m.group(1 if code == "en" else 2), html)
    if "{{" in html:
        raise ValueError("unreplaced placeholder left in output")

    page["file"].parent.mkdir(parents=True, exist_ok=True)
    page["file"].write_text(html, encoding="utf-8", newline="\n")
    return parser.dropped


if __name__ == "__main__":
    for code in PAGES:
        dropped = build(code)
        print(f"{PAGES[code]['file'].relative_to(ROOT)}: removed {dropped} spans of the other language")
