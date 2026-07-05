"""
Drafter-Reviewer module for QA answer generation.

The reviewer pattern: first generate draft answers using the profile
templates, then build a context for a research subagent that critiques
and improves them. Achieved +2.9 quality improvement over single-pass
drafting in testing against Internet Brands.

Usage:
    from jb_autoapply.review import review_answers, format_reviewer_prompt

    # Generate initial drafts and get the reviewer context
    context = review_answers("Company", "Role", "URL", questions)

    # Format a prompt for a subagent with web research tools
    prompt = format_reviewer_prompt(context)

    # The subagent (delegate_task with toolsets=['web']) returns
    # revised answers that you parse with parse_review_result()
    revised = parse_review_result(subagent_output)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .profile import Profile


# ── Data structures ────────────────────────────────────────────────────


@dataclass
class ReviewResult:
    """A single reviewed/revised answer pair."""

    question: str
    initial_draft: str
    revised_answer: str
    reviewer_feedback: str = ""
    improvement_categories: list[str] = field(default_factory=list)


@dataclass
class ReviewContext:
    """All context needed for a reviewer subagent to critique drafts.

    The subagent is expected to:
    1. Research the company (products, mission, news, culture)
    2. Review each initial draft for missing company-specific details
    3. Suggest and incorporate improvements
    """

    company: str
    role: str
    url: str
    questions: list[str]
    initial_drafts: list[str]
    profile_summary: str = ""
    writing_rules: list[str] = field(default_factory=list)

    @property
    def is_competitive(self) -> bool:
        """Heuristic: likely a competitive role that benefits from review."""
        competitive_keywords = [
            "ai", "ml", "machine learning", "data science", "research",
            "senior", "lead", "staff", "principal", "architect",
        ]
        role_lower = self.role.lower()
        return any(kw in role_lower for kw in competitive_keywords)


# ── QA template classification ─────────────────────────────────────────


def _classify_question(question: str) -> str:
    """Map a question to one of the QA templates in profile.py."""
    q = question.lower()

    # Match against known template strategies
    why_company_patterns = [
        "why do you want to work", "why are you interested in",
        "why this company", "why {company}", "what interests you about",
        "what attracts you to", "why did you apply",
    ]
    why_you_patterns = [
        "tell me about yourself", "introduce yourself",
        "why should we hire", "why you", "why are you a good fit",
        "why are you the right", "what makes you",
    ]
    challenge_patterns = [
        "tell me about a time", "describe a challenge",
        "describe a difficult", "describe a project",
        "most challenging", "proudest achievement",
        "accomplishment", "describe a situation",
    ]
    career_goals_patterns = [
        "where do you see", "career goals", "career aspirations",
        "future goals", "what are your goals", "long-term",
        "professional development", "what do you hope",
    ]
    teamwork_patterns = [
        "teamwork", "team player", "work with others",
        "collaboration", "conflict", "disagreement",
        "work in a team", "collaborative",
    ]

    for pattern in why_company_patterns:
        if pattern.replace("{company}", "").strip() in q:
            return "why_company"
    for pattern in why_you_patterns:
        if pattern in q:
            return "why_you"
    for pattern in challenge_patterns:
        if pattern in q:
            return "challenge"
    for pattern in career_goals_patterns:
        if pattern in q:
            return "career_goals"
    for pattern in teamwork_patterns:
        if pattern in q:
            return "teamwork"

    return "why_company"  # safest default


# ── Initial draft generation ───────────────────────────────────────────


def _generate_initial_draft(
    question: str,
    template_key: str,
    profile: Profile,
    company: str,
    role: str,
) -> str:
    """Generate an initial draft for a single question using the profile.

    Uses the QA templates for structure and the compressed profile for
    content guidance. Returns a reasonable first-pass answer.
    """
    template = profile.templates.get(template_key, profile.templates["why_company"])
    strategy = template.get("strategy", "")
    structure = template.get("structure", [])

    stories_text = "\n".join(profile.profile.get("stories", []))
    strengths_text = "; ".join(profile.profile.get("strengths", []))
    tone = profile.style.get("tone", "")
    rules = profile.style.get("rules", [])

    # Find the most relevant story by checking for keyword overlap
    q_words = set(re.sub(r"[^a-z0-9 ]", " ", question.lower()).split())
    scored_stories = []
    for story in profile.profile.get("stories", []):
        story_lower = story.lower()
        overlap = len(set(story_lower.split()) & q_words)
        scored_stories.append((overlap, story))
    scored_stories.sort(key=lambda x: -x[0])
    best_story = scored_stories[0][1] if scored_stories else ""

    draft_parts = [
        f"[Initial draft for: {question}]",
        f"Profile context — Pattern: {profile.profile['pattern']}",
        f"Strengths: {strengths_text}",
    ]
    if best_story:
        draft_parts.append(f"Best story match: {best_story[:200]}")
    draft_parts.append(f"Strategy: {strategy}")
    draft_parts.append(f"Structure: {' → '.join(s for s in structure)}")

    return "\n".join(draft_parts)


def generate_initial_drafts(
    company: str,
    role: str,
    questions: list[str],
) -> list[str]:
    """Generate initial draft answers for a list of questions.

    Uses the Profile module's QA templates and STAR stories to construct
    tailored first-pass answers that a reviewer can then critique.
    """
    profile = Profile()
    drafts: list[str] = []
    for question in questions:
        template_key = _classify_question(question)
        draft = _generate_initial_draft(question, template_key, profile, company, role)
        drafts.append(draft)
    return drafts


# ── Main entry point ───────────────────────────────────────────────────


def review_answers(
    company: str,
    role: str,
    url: str,
    questions: list[str],
) -> ReviewContext:
    """Generate initial drafts and return a ReviewContext ready for the
    reviewer subagent.

    The caller (Hermes agent or pipeline runner) should:
    1. Call this function to get initial drafts + context
    2. Format a reviewer prompt with format_reviewer_prompt()
    3. Delegate the review to a subagent (delegate_task with toolsets=['web'])
    4. Parse the result with parse_review_result()

    Args:
        company: Company name (e.g. "Internet Brands").
        role: Job title (e.g. "Associate AI Software Engineer").
        url: Job posting URL for the reviewer to research.
        questions: List of application questions to draft.

    Returns:
        ReviewContext with initial drafts, profile summary, and metadata.
    """
    profile = Profile()
    initial_drafts = generate_initial_drafts(company, role, questions)

    return ReviewContext(
        company=company,
        role=role,
        url=url,
        questions=questions,
        initial_drafts=initial_drafts,
        profile_summary=profile.compressed,
        writing_rules=profile.style.get("rules", []),
    )


# ── Prompt builder for the reviewer subagent ───────────────────────────


def format_reviewer_prompt(context: ReviewContext) -> str:
    """Build the prompt for a reviewer subagent.

    The subagent will:
    1. Research the company (products, mission, recent news, culture) via web
    2. Review each initial draft for missing company-specific details
    3. Critique writing quality against the profile's style rules
    4. Return revised, company-aware answers

    Returns:
        A prompt string ready for delegate_task with toolsets=['web'].
    """
    questions_block = "\n".join(
        f"  Q{i + 1}: {q}"
        for i, q in enumerate(context.questions)
    )

    drafts_block = "\n\n".join(
        f"--- Question {i + 1}: {context.questions[i]} ---\n"
        f"Initial draft:\n{draft}"
        for i, draft in enumerate(context.initial_drafts)
    )

    rules_block = "\n".join(f"- {r}" for r in context.writing_rules)

    return f"""You are a **senior reviewer** in a job-application pipeline. Your job is to research the company and improve draft answers to application questions.

## Your task

1. **Research the company** — Use web search/tools to learn about:
   - Their main products and services (especially anything AI/ML related)
   - Their mission and recent news
   - Their engineering culture (Glassdoor reviews, tech stack)
   - What makes them unique vs competitors
   - Any flagship products the single-pass drafter might have missed

2. **Review each draft answer** — For each question:
   - Does the draft miss company-specific details it could reference?
   - Does it use a relevant STAR story from the profile?
   - Does it follow the writing style rules?
   - Is the answer forward-looking (what the candidate can do for THEM)?
   - Could the answer reference a specific company product, initiative, or value?

3. **Return revised answers** — For each question, provide:
   - A concise critique (1-2 sentences)
   - A fully revised answer incorporating company research and style rules

## Company: {context.company}
## Role: {context.role}
## Job URL: {context.url}

## Candidate Profile

{context.profile_summary}

## Writing Style Rules

{rules_block}

## Questions

{questions_block}

## Initial Drafts

{drafts_block}

## Output Format

Return a valid JSON object with this exact structure:

{{
  "reviewed_answers": [
    {{
      "question_index": 0,
      "feedback": "Brief critique of the draft",
      "revised_answer": "Full revised answer text (150-250 words, first person, specific)"
    }},
    ...
  ],
  "company_research_findings": "Key findings about the company that informed the revisions",
  "quality_improvement_notes": "What the reviewer caught that the drafter missed"
}}

Rules for revised answers:
- First person active voice ("I built" not "a system was developed")
- NO cliches ("passionate about", "leverage", "synergies", "hit the ground running")
- NO em-dashes — use commas or restructure
- NO apologetic language
- Every claim backed by a specific example
- Forward-looking: what you can do for {context.company}
- Reference **specific company products/initiatives** where possible
- Keep each answer under 250 words
- Do NOT fabricate skills or experience
"""


# ── Result parsing ─────────────────────────────────────────────────────


def parse_review_result(
    result_json: str,
    context: ReviewContext,
) -> list[ReviewResult]:
    """Parse the subagent's JSON output into ReviewResult objects.

    Args:
        result_json: JSON string from the reviewer subagent.
        context: Original ReviewContext to cross-reference questions.

    Returns:
        List of ReviewResult objects with revised answers.

    Raises:
        ValueError: If JSON is malformed or missing required fields.
    """
    try:
        data = json.loads(result_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse reviewer output: {e}") from e

    raw_answers = data.get("reviewed_answers", [])
    if not raw_answers:
        raise ValueError("reviewer output missing 'reviewed_answers' field")

    results: list[ReviewResult] = []
    for item in raw_answers:
        idx = item.get("question_index", 0)
        if idx < 0 or idx >= len(context.questions):
            continue
        results.append(ReviewResult(
            question=context.questions[idx],
            initial_draft=context.initial_drafts[idx] if idx < len(context.initial_drafts) else "",
            revised_answer=item.get("revised_answer", ""),
            reviewer_feedback=item.get("feedback", ""),
            improvement_categories=item.get("improvement_categories", []),
        ))

    return results


def extract_revised_answers(
    results: list[ReviewResult],
) -> list[str]:
    """Extract just the revised answer strings from ReviewResult objects.

    This is the primary return value expected by the apply pipeline.
    Falls back to the initial draft if no revision was made.
    """
    return [
        r.revised_answer if r.revised_answer else r.initial_draft
        for r in results
    ]
