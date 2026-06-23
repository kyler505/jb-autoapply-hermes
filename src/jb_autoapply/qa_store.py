from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from . import config, profile_data
from .profile_data import QAEntry

_STOPWORDS = {
    'the', 'a', 'an', 'and', 'or', 'to', 'of', 'in', 'on', 'for', 'with', 'is',
    'are', 'do', 'you', 'your', 'we', 'our', 'us', 'at', 'this', 'that', 'have',
    'has', 'any', 'be', 'will', 'would', 'can', 'could', 'what', 'why', 'how',
    'when', 'where', 'which', 'who', 'if', 'as', 'it', 'i', 'me', 'my', 'about',
    'please', 'tell', 'describe', 'ever', 'their', 'them', 'there',
}


def _normalize(text: str) -> str:
    return re.sub(r'[^a-z0-9 ]', ' ', text.lower())


def _tokens(text: str) -> set[str]:
    return {w for w in _normalize(text).split() if w and w not in _STOPWORDS}


def _slug(question: str) -> str:
    s = re.sub(r'[^a-z0-9]+', '-', question.lower()).strip('-')
    return (s or 'question')[:60]


def _derive_keywords(question: str, extra: list[str] | None = None) -> list[str]:
    kws = list(dict.fromkeys(list(_tokens(question)) + [w.lower() for w in (extra or [])]))
    full = _normalize(question).strip()
    if full and full not in kws:
        kws.append(full)
    return kws


def find_answer(question: str, threshold: float = 0.6) -> QAEntry | None:
    q_tokens = _tokens(question)
    q_norm = _normalize(question)
    if not q_tokens:
        return None
    best: tuple[float, QAEntry] | None = None
    for entry in profile_data.load_qa_bank():
        if not entry.answer:
            continue
        entry_tokens = _tokens(entry.question) | {t for kw in entry.keywords for t in _tokens(kw)}
        if not entry_tokens:
            continue
        score = len(q_tokens & entry_tokens) / len(q_tokens | entry_tokens)
        for kw in entry.keywords:
            kw_norm = _normalize(kw).strip()
            if len(kw_norm) >= 4 and kw_norm in q_norm:
                score = max(score, 0.75)
        if best is None or score > best[0]:
            best = (score, entry)
    return best[1] if best and best[0] >= threshold else None


def record_answer(question: str, answer: str, *, keywords: list[str] | None = None, category: str = 'learned') -> Path:
    config.QA_DIR.mkdir(parents=True, exist_ok=True)
    existing = find_answer(question, threshold=0.85)
    if existing:
        path = config.QA_DIR / existing.source
    else:
        path = config.QA_DIR / f'{_slug(question)}.md'
        n = 1
        while path.exists():
            path = config.QA_DIR / f'{_slug(question)}-{n}.md'
            n += 1
    kw_lines = '\n'.join(f'  - {k}' for k in _derive_keywords(question, keywords))
    q_escaped = question.replace('"', '\\"')
    content = (
        '---\n'
        'type: qa\n'
        f'question: "{q_escaped}"\n'
        'keywords:\n'
        f'{kw_lines}\n'
        f'category: {category}\n'
        'source: self-heal\n'
        f'recorded: {date.today().isoformat()}\n'
        '---\n\n'
        f'{answer.strip()}\n'
    )
    path.write_text(content, encoding='utf-8')
    return path
