from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from . import config
from .adapters import detect_site
from .vault import update_fields


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class ManualCheckpoint:
    checkpoint_id: str
    created_at: str
    updated_at: str
    status: str
    company: str
    role: str
    site: str
    url: str
    job_path: str
    reason: str
    details: str
    next_step: str
    resume_pdf: str | None
    evidence: list[str]
    resolution_note: str = ''

    def as_dict(self) -> dict[str, Any]:
        return {
            'checkpoint_id': self.checkpoint_id,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'status': self.status,
            'company': self.company,
            'role': self.role,
            'site': self.site,
            'url': self.url,
            'job_path': self.job_path,
            'reason': self.reason,
            'details': self.details,
            'next_step': self.next_step,
            'resume_pdf': self.resume_pdf,
            'evidence': self.evidence,
            'resolution_note': self.resolution_note,
        }


def _checkpoint_path(checkpoint_id: str) -> Path:
    return config.CHECKPOINTS_DIR / f'{checkpoint_id}.json'


def create_checkpoint(
    job: dict[str, Any],
    *,
    reason: str,
    details: str,
    next_step: str,
    evidence: list[str] | None = None,
    resume_pdf: str | None = None,
) -> ManualCheckpoint:
    checkpoint_id = f"cp-{uuid4().hex[:10]}"
    now = _utc_now()
    site = str(job.get('site') or detect_site(str(job.get('url', ''))))
    checkpoint = ManualCheckpoint(
        checkpoint_id=checkpoint_id,
        created_at=now,
        updated_at=now,
        status='pending',
        company=str(job.get('company', '')),
        role=str(job.get('role', '')),
        site=site,
        url=str(job.get('url', '')),
        job_path=str(job.get('path', '')),
        reason=reason,
        details=details,
        next_step=next_step,
        resume_pdf=resume_pdf,
        evidence=list(evidence or []),
    )
    config.CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
    _checkpoint_path(checkpoint_id).write_text(json.dumps(checkpoint.as_dict(), indent=2), encoding='utf-8')
    if checkpoint.job_path:
        update_fields(
            Path(checkpoint.job_path),
            {
                'apply_result': 'manual_required',
                'apply_error': f'{reason}: {details}'.strip(': '),
                'needs_review': True,
            },
        )
    return checkpoint


def list_checkpoints(status: str | None = None) -> list[ManualCheckpoint]:
    if not config.CHECKPOINTS_DIR.exists():
        return []
    items: list[ManualCheckpoint] = []
    for path in sorted(config.CHECKPOINTS_DIR.glob('*.json')):
        data = json.loads(path.read_text(encoding='utf-8'))
        cp = ManualCheckpoint(**data)
        if status and cp.status != status:
            continue
        items.append(cp)
    return items


def resolve_checkpoint(checkpoint_id: str, *, status: str = 'completed', note: str = '') -> ManualCheckpoint:
    path = _checkpoint_path(checkpoint_id)
    if not path.exists():
        raise FileNotFoundError(f'checkpoint not found: {checkpoint_id}')
    data = json.loads(path.read_text(encoding='utf-8'))
    cp = ManualCheckpoint(**data)
    cp.status = status
    cp.updated_at = _utc_now()
    cp.resolution_note = note
    path.write_text(json.dumps(cp.as_dict(), indent=2), encoding='utf-8')
    if cp.job_path:
        update_fields(
            Path(cp.job_path),
            {
                'apply_result': 'ready_to_resume' if status == 'completed' else status,
                'apply_error': note or cp.reason,
                'needs_review': status != 'completed',
            },
        )
    return cp
