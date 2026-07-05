from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import config
from . import nopecha as _nopecha
from .adapters import build_plan, detect_site
from .apply import apply_queue
from .build_resume import compile_resume, resume_name_for_category
from .checkpoints import create_checkpoint, list_checkpoints, resolve_checkpoint
from .prepare import prepare_queue
from .profile_data import load_profile, load_targeting
from . import simplify as _simplify
from . import accounts as _accounts
from . import linkedin as _linkedin
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


def _checkpoint_create(
    job_path: str,
    reason: str,
    details: str,
    next_step: str,
    site: str | None = None,
    url: str | None = None,
    evidence: list[str] | None = None,
    resume_pdf: str | None = None,
) -> int:
    path = Path(job_path)
    job = {
        'path': str(path),
        'company': path.stem,
        'role': path.stem,
        'site': site or detect_site(url or ''),
        'url': url or '',
    }
    checkpoint = create_checkpoint(
        job,
        reason=reason,
        details=details,
        next_step=next_step,
        evidence=evidence,
        resume_pdf=resume_pdf,
    )
    print(f'created checkpoint {checkpoint.checkpoint_id} -> {_checkpoint_summary(checkpoint)}')
    return 0


def _checkpoint_summary(checkpoint) -> str:
    return f"[{checkpoint.status}] {checkpoint.reason} :: {checkpoint.next_step}"


def _checkpoint_list(status: str | None = None) -> int:
    checkpoints = list_checkpoints(None if status == 'all' else status)
    print(f'checkpoints={len(checkpoints)}')
    for cp in checkpoints:
        print(f'- {cp.checkpoint_id} {cp.company} — {cp.role} {_checkpoint_summary(cp)}')
    return 0


def _checkpoint_resolve(checkpoint_id: str, status: str, note: str) -> int:
    checkpoint = resolve_checkpoint(checkpoint_id, status=status, note=note)
    print(f'resolved checkpoint {checkpoint.checkpoint_id} -> {_checkpoint_summary(checkpoint)}')
    return 0


def _nopecha_check() -> int:
    print(_nopecha.status_text())
    return 0 if _nopecha.is_ready() else 1


def _nopecha_download(force: bool) -> int:
    try:
        _nopecha.ensure_extension(force_download=force)
        print(_nopecha.status_text())
        return 0
    except Exception as exc:
        print(f'NopeCHA download failed: {exc}')
        return 1


def _nopecha_setup(key: str) -> int:
    _nopecha.configure_key(key)
    print(_nopecha.status_text())
    return 0


def _simplify_check() -> int:
    print(_simplify.status_text())
    return 0 if _simplify.is_ready() else 1


def _simplify_download(force: bool) -> int:
    try:
        _simplify.ensure_extension(force_download=force)
        print(_simplify.status_text())
        return 0
    except Exception as exc:
        print(f'Simplify download failed: {exc}')
        return 1


def _accounts_list() -> int:
    accts = _accounts.list_accounts()
    if not accts:
        print("No stored ATS accounts.")
        return 0
    print(f"Stored accounts ({len(accts)}):")
    for domain, info in accts.items():
        print(f"  {domain:40s} {info['email']:25s} pwd={info['password']}  ({info['created']})")
    return 0


def _accounts_add(domain: str, email: str, password: str) -> int:
    _accounts.save_account(domain, email, password)
    print(f"Saved account for {domain} ({email})")
    return 0


def _accounts_gen(url: str, email: str) -> int:
    try:
        acct, pwd = _accounts.get_or_create_account(url, email)
        print(f"Account for {acct['domain']}")
        print(f"  Email:    {acct['email']}")
        print(f"  Password: {pwd}")
        return 0
    except ValueError as e:
        print(f"Error: {e}")
        return 1


def _accounts_verify() -> int:
    """Verify all stored Workday credentials."""
    print("Verifying stored Workday credentials...")
    results = _accounts.verify_all_accounts()
    print(f"\nResults ({len(results)} accounts):")
    for r in results:
        icon = "✅" if r["valid"] else "❌"
        print(f"  {icon} {r['company']:20s} ({r.get('domain', '')})")
        print(f"      {r.get('message', r.get('error', 'unknown'))}")
    return 0 if all(r["valid"] for r in results) else 1


def _apply(limit: int | None = None, dry_run: bool = False, evaluate: int = 0, review: bool = False) -> int:
    return apply_queue(limit=limit, dry_run=dry_run, evaluate=evaluate, review=review)


def _linkedin_search(
    keyword: str,
    location: str = "",
    limit: int = 10,
    details: bool = False,
    json_output: bool = False,
) -> int:
    """Search LinkedIn jobs via the public guest API."""
    jobs = _linkedin.cli_search(
        keyword=keyword,
        location=location,
        limit=limit,
        details=details,
        json_output=json_output,
    )
    return 0 if jobs else 1


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
    p = sub.add_parser('checkpoint-create')
    p.add_argument('job_path')
    p.add_argument('--reason', required=True)
    p.add_argument('--details', default='')
    p.add_argument('--next-step', required=True)
    p.add_argument('--site', default=None)
    p.add_argument('--url', default=None)
    p.add_argument('--evidence', action='append', default=[])
    p.add_argument('--resume-pdf', default=None)
    p = sub.add_parser('checkpoint-list')
    p.add_argument('--status', choices=['pending', 'completed', 'skipped', 'all'], default='pending')
    p = sub.add_parser('checkpoint-resolve')
    p.add_argument('checkpoint_id')
    p.add_argument('--status', choices=['completed', 'skipped'], default='completed')
    p.add_argument('--note', default='')
    p = sub.add_parser('nopecha-check')
    p_dl = sub.add_parser('nopecha-download')
    p_dl.add_argument('--force', action='store_true', help='Re-download even if cached')
    p_setup = sub.add_parser('nopecha-setup')
    p_setup.add_argument('key', help='NopeCHA API key')
    sub.add_parser('simplify-check')
    p_sdl = sub.add_parser('simplify-download')
    p_sdl.add_argument('--force', action='store_true', help='Re-download even if cached')
    sub.add_parser('accounts-list')
    p_aadd = sub.add_parser('accounts-add')
    p_aadd.add_argument('domain', help='ATS tenant domain (e.g. cox.wd1.myworkdayjobs.com)')
    p_aadd.add_argument('email')
    p_aadd.add_argument('password')
    p_agen = sub.add_parser('accounts-gen')
    p_agen.add_argument('url', help='Job URL to generate account for')
    p_agen.add_argument('email', nargs='?', default='kcao@tamu.edu')
    sub.add_parser('accounts-verify', help='Verify stored Workday credentials by attempting sign-in')
    p_apply = sub.add_parser('apply', help='Run the apply pipeline on the queue')
    p_apply.add_argument('--limit', type=int, default=None, help='Max jobs to process')
    p_apply.add_argument('--dry-run', action='store_true', help='Preview what would happen without actually submitting')
    p_apply.add_argument('--evaluate', type=int, default=0, metavar='N',
                         help='Score top N jobs with 5-dimension evaluation framework before processing')
    p_apply.add_argument('--review', action='store_true', default=False,
                         help='Run drafter-reviewer on competitive roles before applying')

    p_li = sub.add_parser('linkedin-search', help='Search LinkedIn jobs via the public guest API')
    p_li.add_argument('--keyword', required=True, help='Job search keyword (e.g. "software engineer intern")')
    p_li.add_argument('--location', default='', help='Location (e.g. "Austin, TX")')
    p_li.add_argument('--limit', type=int, default=10, help='Max results to return (default: 10)')
    p_li.add_argument('--details', action='store_true', help='Fetch full job details (descriptions)')
    p_li.add_argument('--json', action='store_true', dest='json_output', help='Output as JSON')

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
    if args.cmd == 'checkpoint-create':
        return _checkpoint_create(
            args.job_path,
            reason=args.reason,
            details=args.details,
            next_step=args.next_step,
            site=args.site,
            url=args.url,
            evidence=args.evidence,
            resume_pdf=args.resume_pdf,
        )
    if args.cmd == 'checkpoint-list':
        return _checkpoint_list(args.status)
    if args.cmd == 'checkpoint-resolve':
        return _checkpoint_resolve(args.checkpoint_id, args.status, args.note)
    if args.cmd == 'nopecha-check':
        return _nopecha_check()
    if args.cmd == 'nopecha-download':
        return _nopecha_download(args.force)
    if args.cmd == 'nopecha-setup':
        return _nopecha_setup(args.key)
    if args.cmd == 'simplify-check':
        return _simplify_check()
    if args.cmd == 'simplify-download':
        return _simplify_download(args.force)
    if args.cmd == 'accounts-list':
        return _accounts_list()
    if args.cmd == 'accounts-add':
        return _accounts_add(args.domain, args.email, args.password)
    if args.cmd == 'accounts-gen':
        return _accounts_gen(args.url, args.email)
    if args.cmd == 'accounts-verify':
        return _accounts_verify()
    if args.cmd == 'apply':
        return _apply(limit=args.limit, dry_run=args.dry_run, evaluate=args.evaluate, review=args.review)
    if args.cmd == 'linkedin-search':
        return _linkedin_search(
            keyword=args.keyword,
            location=args.location,
            limit=args.limit,
            details=args.details,
            json_output=args.json_output,
        )
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
