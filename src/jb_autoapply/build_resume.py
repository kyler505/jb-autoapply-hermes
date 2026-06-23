
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from . import config


def resume_name_for_category(category: str) -> str:
    return 'resume'


def compile_resume(resume_name: str) -> Optional[Path]:
    tex = config.RESUMES_DIR / f'{resume_name}.tex'
    if not tex.exists():
        tex = config.RESUMES_DIR / 'resume.tex'
        if not tex.exists():
            return None
        resume_name = 'resume'

    engine = next((shutil.which(x) for x in ('pdflatex', 'xelatex', 'tectonic') if shutil.which(x)), None)
    config.RESUME_OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = config.RESUME_OUT_DIR / f'{resume_name}.pdf'
    if not engine:
        return None

    if Path(engine).name == 'tectonic':
        subprocess.run([engine, str(tex), '-o', str(config.RESUME_OUT_DIR)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    else:
        subprocess.run([engine, '-interaction=nonstopmode', '-halt-on-error', f'-output-directory={config.RESUME_OUT_DIR}', str(tex)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return out if out.exists() else None
