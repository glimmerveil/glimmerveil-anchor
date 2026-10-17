#!/usr/bin/env python3
"""Transference intake cleaning — shared module for all round-2 readers.

API: clean_text(text) -> (cleaned_text, counts)

counts always carries at least:
  ooc_lines     whole OOC-aside lines removed
  html_tags     HTML tag spans removed
  html_entities HTML character entities decoded
  md_headers    ATX header marks removed
  md_images     image syntax replaced by alt text
  md_links      link syntax replaced by visible text
  md_comments   HTML comments removed
  emptied       messages that became empty after cleaning

Decisions:
  * OOC aside shapes removed ONLY when they occupy a whole line:
      (OOC: ...), ((...)), [OOC]..., lines starting OOC:
    Inline / trailing OOC inside a real line is LEFT ALONE — the line is hers.
  * HTML: tags stripped with a simple <[^>]+> regex; entities decoded with
    html.unescape. We do NOT try to parse real HTML.
  * Markdown STRUCTURE only: ATX headers, links, images, HTML comments.
    Asterisks, underscores, and punctuation runs (e.g. *hugs you*, ...!!)
    are HER VOICE and are NEVER touched.
  * If cleaning leaves only whitespace, cleaned_text is "" and emptied is +1.
    It is the reader's job to drop that message and merge counts into meta.
"""
import html
import re

_OOC_PATTERNS = [
    re.compile(r'^\s*\(OOC:\s*.*\)\s*$', re.IGNORECASE),
    re.compile(r'^\s*\(\(.*\)\)\s*$'),
    re.compile(r'^\s*\[OOC\].*$', re.IGNORECASE),
    re.compile(r'^\s*OOC:\s*.*$', re.IGNORECASE),
]

_MD_HEADER = re.compile(r'^#{1,6}\s+(.*?)(?:\s+#+\s*)?$', re.MULTILINE)
_MD_IMAGE = re.compile(r'!\[([^\]]+)\]\(([^)]+)\)')
_MD_LINK = re.compile(r'(?<!\!)\[([^\]]+)\]\(([^)]+)\)')
_MD_COMMENT = re.compile(r'<!--.*?-->', re.DOTALL)
_HTML_TAG = re.compile(r'<[^>]+>')
_HTML_ENTITY = re.compile(r'&(?:[a-zA-Z][a-zA-Z0-9]*|#[0-9]+|#x[0-9a-fA-F]+);')


def _initial_counts():
    return {
        "ooc_lines": 0,
        "html_tags": 0,
        "html_entities": 0,
        "md_headers": 0,
        "md_images": 0,
        "md_links": 0,
        "md_comments": 0,
        "emptied": 0,
    }


def clean_text(text):
    """Return (cleaned_text, counts) for one intake message.

    See module docstring for the exact shapes removed and the never-touch rule.
    """
    counts = _initial_counts()

    # 1. Whole-line OOC asides only.
    lines = text.splitlines()
    kept = []
    for line in lines:
        if any(pat.match(line) for pat in _OOC_PATTERNS):
            counts["ooc_lines"] += 1
        else:
            kept.append(line)
    cleaned = "\n".join(kept)

    # 2. Markdown structure (before HTML so counts are stable and visible).
    cleaned, n = _MD_COMMENT.subn('', cleaned)
    counts["md_comments"] += n

    cleaned, n = _MD_IMAGE.subn(r'\1', cleaned)
    counts["md_images"] += n

    cleaned, n = _MD_LINK.subn(r'\1', cleaned)
    counts["md_links"] += n

    def _header_replace(m):
        return m.group(1).rstrip()
    cleaned, n = _MD_HEADER.subn(_header_replace, cleaned)
    counts["md_headers"] += n

    # 3. HTML tags and entities.
    tags = _HTML_TAG.findall(cleaned)
    counts["html_tags"] += len(tags)
    cleaned = _HTML_TAG.sub('', cleaned)

    entities = _HTML_ENTITY.findall(cleaned)
    counts["html_entities"] += len(entities)
    cleaned = html.unescape(cleaned)

    # 4. Trim artifact whitespace from structure removal, then drop empties.
    cleaned = cleaned.strip()
    if not cleaned:
        counts["emptied"] += 1

    return cleaned, counts
