from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from . import config, profile_data
from .adapters import build_plan
from .build_resume import compile_resume, resume_name_for_category
from .vault import read_note, set_fm_field, upsert_body_section, write_note


def _substitute(text: str, ctx: dict[str, str]) -> tuple[str, list[str]]:
    import re
    placeholder_re = re.compile(r'\{\{(.*?)\}\}', re.S)
    lower = {k.lower(): v for k, v in ctx.items()}
    unresolved: list[str] = []

    def repl(m: re.Match) -> str:
        raw = m.group(1).strip()
        key = raw.lower()
        if key in lower:
            return lower[key]
        unresolved.append(raw)
        return '{{' + raw + '}}'

    return placeholder_re.sub(repl, text), unresolved


def _qa_answers(ctx: dict[str, str]) -> tuple[str, list[str]]:
    blocks: list[str] = []
    todos: list[str] = []
    for qa in profile_data.load_qa_bank():
        if not qa.answer:
            continue
        rendered, unresolved = _substitute(qa.answer, ctx)
        todos += [f"answer '{qa.question}' -> {{{{{u}}}}}" for u in unresolved]
        blocks.append(f'**Q: {qa.question}**\n\n{rendered}')
    return '\n\n'.join(blocks), todos


def _autofill_block(profile: dict[str, Any]) -> str:
    def g(k: str, default: str = '—') -> str:
        v = profile.get(k)
        return str(v) if v not in (None, '') else default

    rows = [
        ('Full name', f"{g('first_name')} {g('last_name')}"),
        ('Email', g('email')),
        ('Phone', g('phone')),
        ('Current location', g('location')),
        ('LinkedIn', g('linkedin')),
        ('GitHub', g('github')),
        ('Portfolio', g('portfolio')),
        ('School', g('school')),
        ('Degree', g('degree')),
        ('Graduation', g('grad_date')),
        ('Availability', g('availability')),
        ('Work authorization', g('work_authorization')),
        ('Requires sponsorship', 'Yes' if profile.get('requires_sponsorship') else 'No'),
        ('Gender', g('gender')),
        ('Race/ethnicity', g('race_ethnicity')),
        ('Veteran status', g('veteran_status')),
        ('Disability status', g('disability_status')),
    ]
    return '\n'.join(f'- **{label}:** {val}' for label, val in rows)


def prepare_job(job: dict[str, Any], compile_pdf: bool = True) -> dict[str, Any]:
    path = Path(job['path'])
    fm, fm_text, body = read_note(path)
    profile = profile_data.load_profile()
    today = date.today().isoformat()

    company = str(fm.get('company') or job.get('company') or '')
    role = str(fm.get('role') or job.get('role') or '')
    category = str(fm.get('category') or job.get('category') or 'internship')
    plan = build_plan(job)
    ctx = {
        'company': company,
        'role': role,
        'Company': company,
        'team/product': company,
        'Hiring Team / Name': 'Hiring Team',
        'first_name': str(profile.get('first_name', '')),
        'last_name': str(profile.get('last_name', '')),
    }
    resume_name = resume_name_for_category(category)
    pdf_path = compile_resume(resume_name) if compile_pdf else None
    resume_line = f'`{resume_name}.pdf`  (compiled from Profile/Resumes/{resume_name}.tex)' if pdf_path else f'`{resume_name}.tex`  ⚠ PDF not compiled — attach manually'

    template = profile_data.load_cover_template()
    cover, cover_todos = _substitute(template, ctx)
    qa_block, qa_todos = _qa_answers(ctx)
    todos = cover_todos + qa_todos
    todo_md = '\n'.join(f'- [ ] ⚠ Resolve placeholder in {t}' for t in dict.fromkeys(todos)) if todos else '- [x] No unresolved placeholders'
    browser_profile_md = '\n'.join(
        [
            f"- **Mode:** {plan.browser_profile['mode']}",
            f"- **Action pacing:** {plan.browser_profile['action_delay_ms']['min']}-{plan.browser_profile['action_delay_ms']['max']} ms between actions",
            f"- **Settle after actions:** {plan.browser_profile['post_action_settle_ms']} ms",
            f"- **Settle after uploads:** {plan.browser_profile['post_upload_settle_ms']} ms",
            f"- **Re-scan each step:** {'Yes' if plan.browser_profile['per_step_rescan'] else 'No'}",
        ]
        + [f'- {item}' for item in plan.browser_profile['input_strategy']]
    )
    checkpoint_md = '\n'.join(
        f"- **{item['kind']}:** {item['trigger']} → {item['action']}" for item in plan.manual_checkpoints
    )
    apply_steps_md = '\n'.join(f'- {step}' for step in plan.steps)

    content = f'''**Apply URL:** {fm.get('url', '—')}
**Resume:** {resume_line}
**State:** prepared — assisted apply with human checkpoints

### Autofill data
{_autofill_block(profile)}

### Assisted apply steps
{apply_steps_md}

### Legitimate browser behavior profile
{browser_profile_md}

### Human checkpoints
{checkpoint_md}

### Screening answers (from Q&A bank)
{qa_block or '_No reusable answers available yet — add notes to Profile/QA/._'}

### Cover letter (draft)
{cover}

### Review checklist
- [ ] Company name correct everywhere
- [ ] Role title matches the posting exactly
- [ ] "Why this company" line is specific, not generic
- [ ] One quantified accomplishment included
- [ ] Resume attached and correct version
- [ ] Work-authorization / sponsorship answer correct
- [ ] EEO answers reflect your choices
{todo_md}
'''
    body = upsert_body_section(body, f'Application {today}', content)
    fm_text = set_fm_field(fm_text, 'resume_used', resume_name)
    fm_text = set_fm_field(fm_text, 'apply_method', f'assisted-{plan.site}')
    fm_text = set_fm_field(fm_text, 'needs_review', True)
    write_note(path, fm_text, body)
    return {'file': path.name, 'company': company, 'role': role, 'resume': resume_name, 'pdf': str(pdf_path) if pdf_path else None, 'unresolved': list(dict.fromkeys(todos))}


def prepare_queue(limit: int | None = None, compile_pdf: bool = True) -> list[dict[str, Any]]:
    queue = json.loads(config.QUEUE_JSON.read_text(encoding='utf-8'))
    if limit:
        queue = queue[:limit]
    return [prepare_job(job, compile_pdf=compile_pdf) for job in queue]
