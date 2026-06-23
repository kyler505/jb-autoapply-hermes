from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

FM_RE = re.compile(r'^---\n(.*?)\n---\n?(.*)$', re.S)


def split_note(text: str) -> tuple[str, str]:
    m = FM_RE.match(text)
    if not m:
        return '', text
    return m.group(1), m.group(2)


def parse_frontmatter(text: str) -> dict[str, Any]:
    fm, _ = split_note(text)
    if not fm:
        return {}
    try:
        data = yaml.safe_load(fm)
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError:
        return {}


def read_note(path: Path) -> tuple[dict[str, Any], str, str]:
    text = path.read_text(encoding='utf-8')
    fm_text, body = split_note(text)
    return parse_frontmatter(text), fm_text, body


def _format_scalar(value: Any) -> str:
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value)
    if s == '' or re.search(r'[:#\[\]{}&*!|>\'\"%@`]', s) or s.strip() != s:
        return '"' + s.replace('"', '\\"') + '"'
    return s


def set_fm_field(fm_text: str, key: str, value: Any) -> str:
    line = f'{key}: {_format_scalar(value)}'
    pattern = re.compile(rf'(?m)^{re.escape(key)}:.*$')
    if pattern.search(fm_text):
        return pattern.sub(line, fm_text, count=1)
    sep = '' if fm_text.endswith('\n') or fm_text == '' else '\n'
    return f'{fm_text}{sep}{line}'


def write_note(path: Path, fm_text: str, body: str) -> None:
    body = body.lstrip('\n')
    text = f'---\n{fm_text}\n---\n\n{body}' if body else f'---\n{fm_text}\n---\n'
    path.write_text(text, encoding='utf-8')


def upsert_body_section(body: str, header: str, content: str) -> str:
    marker = f'## {header}'
    lines = body.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.strip() == marker:
            start = i
            break
    block = f'{marker}\n\n{content.rstrip()}\n'
    if start is None:
        sep = '' if body.endswith('\n\n') or body == '' else ('\n' if body.endswith('\n') else '\n\n')
        return f'{body}{sep}{block}'
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith('## '):
            end = j
            break
    new_lines = lines[:start] + block.splitlines() + [''] + lines[end:]
    return '\n'.join(new_lines).rstrip() + '\n'


def update_fields(path: Path, fields: dict[str, Any]) -> None:
    _, fm_text, body = read_note(path)
    for k, v in fields.items():
        fm_text = set_fm_field(fm_text, k, v)
    write_note(path, fm_text, body)
