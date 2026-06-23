from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import config, profile_data
from .vault import read_note, update_fields


def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    return [str(v)]


def _parse_date(v: Any) -> date | None:
    if not v:
        return None
    for fmt in ('%Y-%m-%d', '%Y-%m'):
        try:
            return datetime.strptime(str(v), fmt).date()
        except ValueError:
            pass
    return None


def passes_filters(fm: dict[str, Any], t: dict[str, Any]) -> bool:
    if fm.get('active') is not True:
        return False
    if str(fm.get('status', '')) != 'to-apply':
        return False
    category = str(fm.get('category', ''))
    if t['include_categories'] and category not in t['include_categories']:
        return False
    company = str(fm.get('company', '')).strip().lower()
    if company in {c.lower() for c in t['exclude_companies']}:
        return False
    role = str(fm.get('role', '')).lower()
    if any(kw.lower() in role for kw in t['exclude_keywords']):
        return False
    inc_terms = {str(x).lower() for x in t['include_terms']}
    if category == 'internship' and inc_terms:
        job_terms = {x.lower() for x in _as_list(fm.get('terms'))}
        if not (job_terms & inc_terms):
            return False
    inc_locs = {str(x).lower() for x in t['include_locations']}
    if inc_locs:
        job_locs = {x.lower() for x in _as_list(fm.get('locations'))}
        if not any(any(il in jl for jl in job_locs) for il in inc_locs):
            return False
    return True


def score(fm: dict[str, Any], t: dict[str, Any]) -> tuple[float, dict[str, float]]:
    breakdown: dict[str, float] = {}
    discipline = str(fm.get('discipline', 'other'))
    breakdown['discipline'] = config.DISCIPLINE_WEIGHTS.get(discipline, 5)
    category = str(fm.get('category', ''))
    breakdown['category'] = config.CATEGORY_WEIGHTS.get(category, 0)
    posted = _parse_date(fm.get('date_posted'))
    if posted:
        days = max((date.today() - posted).days, 0)
        decay = math.pow(0.5, days / config.RECENCY_HALF_LIFE_DAYS)
        breakdown['recency'] = round(config.RECENCY_MAX_POINTS * decay, 2)
    else:
        breakdown['recency'] = 0.0
    inc_locs = {str(x).lower() for x in t['include_locations']}
    if inc_locs:
        job_locs = {x.lower() for x in _as_list(fm.get('locations'))}
        if any(any(il in jl for jl in job_locs) for il in inc_locs):
            breakdown['location'] = config.LOCATION_MATCH_BONUS
    return round(sum(breakdown.values()), 2), breakdown


def _write_queue_md(queue: list[dict[str, Any]], total_candidates: int, cap: int) -> None:
    lines = [
        '# Daily apply queue',
        '',
        f'Generated {datetime.now():%Y-%m-%d %H:%M} · {len(queue)} of {total_candidates} eligible jobs (cap {cap})',
        '',
        '| # | Priority | Company | Role | Disc | Category | Location | URL |',
        '|---|----------|---------|------|------|----------|----------|-----|',
    ]
    for i, c in enumerate(queue, 1):
        loc = ', '.join(c['locations'][:2]) or '—'
        lines.append(f"| {i} | {c['priority']} | {c['company']} | {c['role']} | {c['discipline']} | {c['category']} | {loc} | {c['url']} |")
    config.QUEUE_MD.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def build_queue(write_priority: bool = True) -> list[dict[str, Any]]:
    t = profile_data.load_targeting()
    candidates: list[dict[str, Any]] = []
    for path in sorted(config.JOBS_DIR.glob('*.md')):
        fm, _, _ = read_note(path)
        if not passes_filters(fm, t):
            continue
        total, breakdown = score(fm, t)
        candidates.append({
            'file': path.name,
            'path': str(path),
            'company': fm.get('company'),
            'role': fm.get('role'),
            'category': fm.get('category'),
            'discipline': fm.get('discipline'),
            'locations': _as_list(fm.get('locations')),
            'terms': _as_list(fm.get('terms')),
            'url': fm.get('url'),
            'date_posted': str(fm.get('date_posted')),
            'priority': total,
            'score_breakdown': breakdown,
        })
    candidates.sort(key=lambda c: (-c['priority'], str(c['company']), str(c['role'])))
    if write_priority:
        for c in candidates[: config.PRIORITY_WRITE_LIMIT]:
            update_fields(Path(c['path']), {'priority': c['priority']})
    cap = int(t.get('daily_cap', 25))
    queue = candidates[:cap]
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    config.QUEUE_JSON.write_text(json.dumps(queue, indent=2), encoding='utf-8')
    _write_queue_md(queue, len(candidates), cap)
    return queue
