"""
5-dimension job evaluation framework.

Scores jobs on: Technical Skills Match, Experience Match, Behavioral Fit,
Location & Logistics, Career Alignment — with weighted composite score.

Designed as an optional enrichment step: run on the top N queue jobs
before processing to skip poor fits and prioritize strong matches.

Usage:
    from jb_autoapply.evaluate import evaluate_job
    score, breakdown, diagnostics = await evaluate_job(url, "Company", "Role")
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# ── Evaluation dimensions ─────────────────────────────────────────────

DIMENSIONS = [
    "technical_skills",
    "experience_match",
    "behavioral_fit",
    "career_alignment",
]

PASS_FAIL = ["location"]

WEIGHTS = {
    "technical_skills": 0.30,
    "experience_match": 0.25,
    "behavioral_fit": 0.15,
    "career_alignment": 0.30,
    # Location is pass/fail (not weighted, but blocks scoring)
}


@dataclass
class Evaluation:
    job_url: str
    company: str
    role: str

    # Scored 0-100
    technical_skills: int | None = None
    experience_match: int | None = None
    behavioral_fit: int | None = None
    career_alignment: int | None = None

    # Pass/Fail
    location: str | None = None  # "pass" or "fail"

    # Diagnostics
    company_research: str = ""
    skill_gaps: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    notes: str = ""

    @property
    def weighted_score(self) -> float | None:
        """Return weighted composite, or None if location fails."""
        if self.location and self.location != "pass":
            return None

        total = 0.0
        dims = [d for d in DIMENSIONS if getattr(self, d) is not None]
        if not dims:
            return None
        for d in dims:
            v = getattr(self, d)
            if v is not None:
                total += v * WEIGHTS.get(d, 0)
        return round(total, 1)

    @property
    def category(self) -> str:
        ws = self.weighted_score
        if ws is None:
            if self.location and self.location == "fail":
                return "location_blocked"
            return "insufficient_data"
        if ws >= 75:
            return "strong"
        elif ws >= 60:
            return "good"
        elif ws >= 45:
            return "moderate"
        elif ws >= 30:
            return "weak"
        else:
            return "poor"

    def summary(self) -> str:
        """Return a one-line summary for queue display."""
        cat = self.category
        ws = self.weighted_score
        score_str = f"{ws}/100" if ws is not None else "BLOCKED"
        return f"[{cat.upper():17s}] {score_str:>9s} | {self.company:25s} | {self.role}"


# ── Prompt template ──────────────────────────────────────────────────

CANDIDATE_PROFILE = """Kyler Cao — Texas A&M CS+Business 2027. Cypress TX (Houston area).
Current: Product & Engineering Intern at Global Shop Solutions (ERP software).
Skills: Python, ML/data science (scikit-learn, TensorFlow basics), React/Next.js, full-stack web dev, automated pipelines with Playwright, git, Linux.
US citizen, no sponsorship needed. Open to relocation for the right role.
Interests: AI/ML engineering, backend systems, automation, building things that ship."""

EVALUATION_PROMPT = """You are a job fit evaluator for the auto-apply pipeline.

## Candidate
{CANDIDATE_PROFILE}

## Job
Company: {company}
Role: {role}
URL: {url}

## Instructions
1. Fetch the job posting URL to get the full description (use web_extract or browser)
2. Research the company (Glassdoor, Comparably, company site, recent news)
3. Score the job on these 5 dimensions:

### Scoring Guide
**Technical Skills Match (0-100):** How well required skills match candidate's skills.
0-30: Major gap — missing most required skills
31-50: Partial — covers some but several gaps
51-70: Good alignment — most skills present, minor gaps
71-85: Strong — all core skills present, bonus skills too
86-100: Exceptional — overqualified

**Experience Match (0-100):** Work history alignment.
0-30: Wrong level (too senior/junior)
31-50: Adjacent but not directly relevant
51-70: Relevant experience, appropriate level
71-85: Strong track record in similar roles
86-100: Perfect background match

**Behavioral Fit (0-100):** Culture, work style, values.
Consider Glassdoor reviews, culture scores, management philosophy.
0-30: Toxic culture red flags
31-50: Mixed reviews, risks
51-70: Average culture, no red flags
71-85: Good culture match
86-100: Excellent alignment with how candidate works best

**Career Alignment (0-100):** Does this advance the candidate's career trajectory?
0-30: Dead end role, no growth
31-50: Stepping stone at best
51-70: Good learning opportunity
71-85: Excellent career move
86-100: Dream role for trajectory

**Location (pass/fail):** Can the candidate work here?
- "pass" -> remote, local (Texas), or candidate is willing to relocate
- "fail" -> wrong country, commute impossible, relocation not feasible

### Output Format
Return a JSON object exactly like:
{{
  "technical_skills": 75,
  "experience_match": 80,
  "behavioral_fit": 50,
  "career_alignment": 68,
  "location": "pass",
  "company_research": "Internet Brands is a KKR-backed...",
  "skill_gaps": ["agentic AI", "prompt engineering"],
  "strengths": ["Python alignment", "entry-level fit"],
  "red_flags": ["$60k in El Segundo", "Glassdoor 2.7/5 culture"],
  "notes": "Apply with caveats — strong role alignment but culture concerns"
}}

Score truthfully. If you can't fetch the posting or do sufficient research, report the dimensions you can score and note the gaps."""


async def evaluate_job(
    url: str,
    company: str,
    role: str,
) -> Evaluation:
    """Evaluate a single job posting using the 5-dimension framework.

    In the default mode, this generates the evaluation prompt and returns it
    as an Evaluation with notes set to 'needs LLM evaluation'.
    The actual LLM scoring is done by a subagent when --evaluate N is passed.
    """
    ev = Evaluation(job_url=url, company=company, role=role)
    return ev


def format_evaluation_prompt(company: str, role: str, url: str) -> str:
    """Generate the prompt for a subagent to evaluate this job."""
    return EVALUATION_PROMPT.format(
        CANDIDATE_PROFILE=CANDIDATE_PROFILE,
        company=company,
        role=role,
        url=url,
    )


def parse_evaluation(result_json: str) -> Evaluation:
    """Parse a subagent's JSON evaluation result into an Evaluation object."""
    data = json.loads(result_json)
    return Evaluation(
        job_url="",
        company="",
        role="",
        technical_skills=data.get("technical_skills"),
        experience_match=data.get("experience_match"),
        behavioral_fit=data.get("behavioral_fit"),
        career_alignment=data.get("career_alignment"),
        location=data.get("location"),
        company_research=data.get("company_research", ""),
        skill_gaps=data.get("skill_gaps", []),
        strengths=data.get("strengths", []),
        red_flags=data.get("red_flags", []),
        notes=data.get("notes", ""),
    )
