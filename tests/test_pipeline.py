
from __future__ import annotations

import pytest

from jb_autoapply import config
from jb_autoapply.adapters import build_plan
from jb_autoapply.checkpoints import create_checkpoint, list_checkpoints, resolve_checkpoint
from jb_autoapply.prepare import prepare_job
from jb_autoapply.qa_store import find_answer, record_answer
from jb_autoapply.selector import build_queue


@pytest.fixture()
def temp_vault(tmp_path, monkeypatch):
    vault = tmp_path / 'jb'
    (vault / 'Jobs').mkdir(parents=True)
    (vault / 'Profile' / 'QA').mkdir(parents=True)
    (vault / 'Profile' / 'Resumes').mkdir(parents=True)
    (vault / 'Profile' / 'Materials').mkdir(parents=True)

    (vault / 'Profile' / 'Profile.md').write_text('''---
first_name: Kyler
last_name: Cao
email: k@example.com
phone: '123'
location: Texas
requires_sponsorship: true
---
''', encoding='utf-8')
    (vault / 'Profile' / 'Targeting.md').write_text('''---
include_categories: [internship, new-grad]
daily_cap: 5
resume_by_category: {}
---
''', encoding='utf-8')
    (vault / 'Profile' / 'Materials' / 'Cover Letter Template.md').write_text('''---
---
Dear {{company}} team,
---
I am excited to apply to {{role}} at {{company}}.
---
Best, {{first_name}}
''', encoding='utf-8')
    (vault / 'Profile' / 'QA' / 'auth.md').write_text('''---
question: work authorization
keywords: [work authorization]
category: learned
source: test
---
Yes
''', encoding='utf-8')
    (vault / 'Profile' / 'Resumes' / 'resume.tex').write_text('''\documentclass{article}\begin{document}resume\end{document}
''', encoding='utf-8')
    (vault / 'Jobs' / 'A.md').write_text('''---
company: Alpha
role: SWE Intern
category: internship
discipline: swe
active: true
status: to-apply
locations: [Remote]
date_posted: '2026-06-20'
url: https://jobs.ashbyhq.com/alpha/apply
---
body
''', encoding='utf-8')
    (vault / 'Jobs' / 'B.md').write_text('''---
company: Beta
role: Data Scientist
category: internship
discipline: data
active: false
status: to-apply
locations: [Remote]
date_posted: '2026-06-20'
url: https://jobs.lever.co/beta/apply
---
body
''', encoding='utf-8')
    monkeypatch.setenv('JB_VAULT', str(vault))

    # The pipeline modules read config constants at import time, so patch them
    # directly for the isolated test vault.
    config.VAULT = vault
    config.JOBS_DIR = vault / 'Jobs'
    config.PROFILE_DIR = vault / 'Profile'
    config.PROFILE_MD = vault / 'Profile' / 'Profile.md'
    config.TARGETING_MD = vault / 'Profile' / 'Targeting.md'
    config.QA_DIR = vault / 'Profile' / 'QA'
    config.RESUMES_DIR = vault / 'Profile' / 'Resumes'
    config.MATERIALS_DIR = vault / 'Profile' / 'Materials'
    config.COVER_TEMPLATE = vault / 'Profile' / 'Materials' / 'Cover Letter Template.md'
    config.OUT_DIR = tmp_path / 'out'
    config.QUEUE_JSON = config.OUT_DIR / 'queue.json'
    config.QUEUE_MD = config.OUT_DIR / 'queue.md'
    config.PLAN_JSON = config.OUT_DIR / 'plan.json'
    config.RESUME_OUT_DIR = config.OUT_DIR / 'resumes'
    config.CHECKPOINTS_DIR = config.OUT_DIR / 'checkpoints'
    return vault


def test_queue_filters_and_scores(temp_vault):
    q = build_queue(write_priority=False)
    assert len(q) == 1
    assert q[0]['company'] == 'Alpha'
    assert q[0]['priority'] > 0
    assert config.QUEUE_JSON.exists()
    assert config.QUEUE_MD.exists()


def test_prepare_writes_application_packet(temp_vault):
    q = build_queue(write_priority=False)
    result = prepare_job(q[0], compile_pdf=False)
    note = (temp_vault / 'Jobs' / 'A.md').read_text(encoding='utf-8')
    assert '## Application' in note
    assert 'Apply URL' in note
    assert 'Legitimate browser behavior profile' in note
    assert 'Human checkpoints' in note
    assert result['resume'] == 'resume'
    assert 'resume_used' in note


def test_build_plan_contains_assisted_browser_and_checkpoint_policy(temp_vault):
    q = build_queue(write_priority=False)
    plan = build_plan(q[0]).as_dict()
    assert plan['browser_profile']['mode'] == 'assisted'
    assert plan['browser_profile']['per_step_rescan'] is True
    assert 'nopecha_enabled' in plan['browser_profile']
    assert 'nopecha_enabled' in plan
    assert isinstance(plan['nopecha_enabled'], bool)


def test_checkpoint_roundtrip_updates_job_note(temp_vault):
    q = build_queue(write_priority=False)
    checkpoint = create_checkpoint(
        q[0],
        reason='captcha',
        details='Visible anti-bot challenge on apply form',
        next_step='Wait for user to clear challenge and then resume on review step',
        evidence=['/tmp/captcha.png'],
        resume_pdf='/tmp/resume.pdf',
    )
    pending = list_checkpoints('pending')
    assert len(pending) == 1
    assert pending[0].checkpoint_id == checkpoint.checkpoint_id
    note = (temp_vault / 'Jobs' / 'A.md').read_text(encoding='utf-8')
    assert 'manual_required' in note
    resolved = resolve_checkpoint(checkpoint.checkpoint_id, note='User cleared challenge')
    assert resolved.status == 'completed'
    note = (temp_vault / 'Jobs' / 'A.md').read_text(encoding='utf-8')
    assert 'ready_to_resume' in note


def test_qa_store_roundtrip(temp_vault):
    path = record_answer('Expected work authorization?', 'No sponsorship required')
    assert path.exists()
    hit = find_answer('What is your expected work authorization?')
    assert hit is not None
    assert 'No sponsorship' in hit.answer


def test_build_plan_nopecha_disabled_drops_challenge_checkpoint(temp_vault, monkeypatch):
    """When NopeCHA is not ready, the challenge checkpoint is present."""
    monkeypatch.setattr('jb_autoapply.nopecha.is_ready', lambda: False)

    q = build_queue(write_priority=False)
    plan = build_plan(q[0]).as_dict()
    assert plan['nopecha_enabled'] is False
    kinds = [c['kind'] for c in plan['manual_checkpoints']]
    assert 'challenge' in kinds
    assert 'verification' in kinds
    assert 'final-review' in kinds
    assert 'challenge_signals' in plan['browser_profile']
    assert len(plan['browser_profile']['challenge_signals']) > 0
    assert 'captcha' in plan['browser_profile']['challenge_signals']


def test_build_plan_nopecha_enabled_skips_challenge_checkpoint(temp_vault, monkeypatch):
    """When NopeCHA is ready, the challenge checkpoint is omitted and nopecha_args are present."""
    monkeypatch.setattr('jb_autoapply.nopecha.is_ready', lambda: True)
    monkeypatch.setattr(
        'jb_autoapply.nopecha.playwright_args',
        lambda ext_path=None: ['--load-extension=/mock/nopecha', '--no-sandbox'],
    )

    q = build_queue(write_priority=False)
    plan = build_plan(q[0]).as_dict()
    assert plan['nopecha_enabled'] is True
    kinds = [c['kind'] for c in plan['manual_checkpoints']]
    assert 'challenge' not in kinds
    assert 'verification' in kinds
    assert 'final-review' in kinds
    bp = plan['browser_profile']
    assert bp['nopecha_enabled'] is True
    assert 'nopecha_args' in bp
    assert any('load-extension=' in a for a in bp['nopecha_args'])
    # When NopeCHA is enabled, challenge_signals should be empty
    assert len(bp.get('challenge_signals', [])) == 0

