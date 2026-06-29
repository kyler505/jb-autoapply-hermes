
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VAULT = Path.home() / 'Obsidian' / 'jb'
VAULT = Path(os.environ.get('JB_VAULT', DEFAULT_VAULT)).expanduser().resolve()

JOBS_DIR = VAULT / 'Jobs'
PROFILE_DIR = VAULT / 'Profile'
PROFILE_MD = PROFILE_DIR / 'Profile.md'
TARGETING_MD = PROFILE_DIR / 'Targeting.md'
QA_DIR = PROFILE_DIR / 'QA'
RESUMES_DIR = PROFILE_DIR / 'Resumes'
MATERIALS_DIR = PROFILE_DIR / 'Materials'
COVER_TEMPLATE = MATERIALS_DIR / 'Cover Letter Template.md'

OUT_DIR = REPO_ROOT / 'out'
QUEUE_JSON = OUT_DIR / 'queue.json'
QUEUE_MD = OUT_DIR / 'queue.md'
PLAN_JSON = OUT_DIR / 'plan.json'
RESUME_OUT_DIR = OUT_DIR / 'resumes'
CHECKPOINTS_DIR = OUT_DIR / 'checkpoints'

DISCIPLINE_WEIGHTS = {
    'swe': 30,
    'ml': 28,
    'backend': 26,
    'data': 24,
    'frontend': 22,
    'mobile': 18,
    'devops': 18,
    'security': 16,
    'hardware': 8,
    'other': 6,
}
CATEGORY_WEIGHTS = {'internship': 12, 'new-grad': 10}
RECENCY_MAX_POINTS = 20
RECENCY_HALF_LIFE_DAYS = 21
LOCATION_MATCH_BONUS = 15
PRIORITY_WRITE_LIMIT = 200
WRITEBACK_FIELDS = ['priority', 'apply_method', 'apply_result', 'apply_error', 'confirmation', 'resume_used', 'needs_review']
