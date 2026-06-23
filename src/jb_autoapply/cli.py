from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import config
from .adapters import build_plan
from .build_resume import compile_resume, resume_name_for_category
from .prepare import prepare_queue
from .profile_data import load_profile, load_targeting
from .selector import build_queue


def _doctor() -> int:
    issues: list[str] = []
    if not config.VAULT.exists():
        issues.append(f'vault missing: {config.VAULT}')
    for path in [config.JOBS_DIR, config.PROFILE_DIR, config.PROFILE_MD, config.TARGETING_MD]:
        if not Path(path).exists():
            issues.append(f'missing required path: {path}')
    profile = load_profile() if config.PROFILE_MD.exists() else {}
    targeting = load_targeting() if config.TARGETING_MD.exists() else {}
    print(f'vault={config.VAULT}')
    print(f'jobs={config.JOBS_DIR if config.JOBS_DIR.exists() else "missing"}')
    print(f'profile_keys={sorted(profile.keys())[:12]}')
    print(f'targeting_keys={sorted(targeting.keys())[:12]}')
    if issues:
        print('issues:')
        for i in issues:
            print(f'- {i}')
        return 1
    print('doctor: ok')
    return 0


def _queue(limit: int | None = None) -> int:
    q = build_queue()
    print(f'queued {len(q)} jobs -> {config.QUEUE_MD}')
    for i, item in enumerate(q[: limit or len(q)], 1):
        print(f"{i:>2}. [{item['priority']}] {item['company']} — {item['role']}")
    return 0


def _prepare(limit: int | None = None) -> int:
    results = prepare_queue(limit=limit)
    print(f'prepared {len(results)} packets')
    for r in results:
        flag = f" ⚠ {len(r['unresolved'])} placeholder(s)" if r['unresolved'] else ''
        print(f"- {r['company']} — {r['role']} [{r['resume']}] {flag}")
    return 0


def _plan(limit: int | None = None) -> int:
    q = build_queue()
    if limit:
        q = q[:limit]
    plans = [build_plan(item).as_dict() for item in q]
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    config.PLAN_JSON.write_text(json.dumps(plans, indent=2), encoding='utf-8')
    print(f'wrote {len(plans)} plans -> {config.PLAN_JSON}')
    for plan in plans:
        print(f"- {plan['site']}: {plan['url']}")
    return 0


def _resume(category: str) -> int:
    name = resume_name_for_category(category)
    pdf = compile_resume(name)
    print(str(pdf) if pdf else f'no pdf compiled for {name}')
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog='jb-autoapply')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('doctor')
    p = sub.add_parser('queue')
    p.add_argument('--limit', type=int, default=None)
    p = sub.add_parser('prepare')
    p.add_argument('--limit', type=int, default=None)
    p = sub.add_parser('plan')
    p.add_argument('--limit', type=int, default=None)
    p = sub.add_parser('resume')
    p.add_argument('category', nargs='?', default='resume')

    args = ap.parse_args(argv)
    if args.cmd == 'doctor':
        return _doctor()
    if args.cmd == 'queue':
        return _queue(args.limit)
    if args.cmd == 'prepare':
        return _prepare(args.limit)
    if args.cmd == 'plan':
        return _plan(args.limit)
    if args.cmd == 'resume':
        return _resume(args.category)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
