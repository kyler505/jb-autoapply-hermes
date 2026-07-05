"""
Candidate profile module for auto-fill QA answers.

Sources: behavioral profile + writing-style-compliant answer templates.
Generates per-job tailored answers for common application questions.

Usage:
    from jb_autoapply.profile import Profile
    profile = Profile()
    answer = profile.answer_for("Why do you want to work here?", company="Acme Corp")
"""

import json
from pathlib import Path

# ── Compressed profile (auto-fill cheat sheet) ──────────────────────────

BEHAVIORAL_PROFILE = {
    "pattern": "Builder-Automator",
    "drives": [
        "End-to-end ownership — works best with clear goal + freedom to choose approach",
        "Practical problem-solving — motivated by tangible shipped outcomes",
        "Learning through building — absorbs tools fastest with a concrete deliverable",
        "Moderate-high collaboration — values complementary teammates, defaults to solo deep-work",
    ],
    "strengths": [
        "End-to-end execution: idea → deployed → documented",
        "Rapid prototyping: Python + ML to working version fast, iterate on feedback",
        "Cross-discipline bridging: CS + Business, can explain in technical and ROI terms",
    ],
    "stories": [
        "({tag}) Built an adapter layer that auto-detected ERP export format changes and remapped fields on the fly, dropping pipeline failures from weekly to near-zero over months",
        "({tag}) Automated a multi-step manual workflow at Global Shop Solutions using Python scripts and internal APIs, reducing processing time by a significant margin",
        "({tag}) Set up a daily job scraping pipeline that processes 40+ job postings, fills ATS forms automatically, and marks applied jobs with verification",
    ],
    "work_style": [
        "Clear problem definition + success criteria up front, then autonomy to design",
        "Direct user feedback loops — wants to talk to people who use what's built",
        "Solo deep-work blocks with structured collaboration checkpoints",
        "Shipping working code valued over process theater",
    ],
    "growth_areas": [
        "Depth over breadth — wide toolkit, actively deepening ML engineering skills",
        "Delegation instinct — owns problems through, learning when to loop in specialists",
    ],
}

WRITING_STYLE = {
    "tone": "warm but direct. conversational professional, not stiff corporate-speak",
    "voice": "first person active voice ('I built' not 'a system was developed')",
    "rules": [
        "NO cliches: cut 'passionate about', 'leverage', 'synergies', 'hit the ground running'",
        "NO em-dashes — use commas or restructure",
        "NO apologetic language: not 'I think I could' but 'I bring X, demonstrated by Y'",
        "Demonstrate don't state: every claim backed by a specific example",
        "Forward-looking: focus on what you can do for the employer, not what you want",
        "Don't fabricate skills or experience — frame adjacent experience honestly",
    ],
}

QA_TEMPLATES = {
    "why_you": {
        "strategy": "Lead with what you've built, connect it to what the company needs",
        "structure": [
            "Opening sentence: your current stage + what you're looking for",
            "Concrete example from internship or project showing relevant skill",
            "What you found satisfying about that example (connects to job's context)",
            "Closing: what this company specifically offers that aligns with your trajectory",
        ],
    },
    "why_company": {
        "strategy": "Reference what the company does (verified via web search if possible), connect your background to their mission",
        "structure": [
            "Something specific about the company's products/mission that interests you",
            "How your background maps to their needs — concrete, not generic",
            "What you'd want to contribute (forward-looking)",
        ],
    },
    "challenge": {
        "strategy": "STAR from one of the tagged stories above. Pick the one closest to the job's domain",
        "structure": [
            "Situation: what was wrong or inefficient",
            "Task: what needed to happen",
            "Action: what you specifically built (not just 'I fixed it')",
            "Result: quantifiable outcome",
            "Lesson: broader principle learned",
        ],
    },
    "career_goals": {
        "strategy": "Show trajectory from current skills toward the job's requirements",
        "structure": [
            "Current strength area (prototyping, automation, building)",
            "What you're actively developing (deployment, monitoring, production engineering)",
            "How this role fits that trajectory",
            "Longer-term direction without overpromising",
        ],
    },
    "teamwork": {
        "strategy": "Honest about solo-preference but show you're effective in team contexts",
        "structure": [
            "How you prefer to work (owning a clear piece, clean handoffs)",
            "Example of coordinating successfully",
            "How you handle disagreements (data-driven pushback)",
            "How you unblock teammates",
        ],
    },
}


class Profile:
    """Candidate profile for generating auto-fill answers."""

    def __init__(self, profile_path=None):
        self.profile = BEHAVIORAL_PROFILE
        self.style = WRITING_STYLE
        self.templates = QA_TEMPLATES

    @property
    def compressed(self):
        """Return a short profile string for injection into auto-fill prompts."""
        lines = [
            f"Pattern: {self.profile['pattern']}",
            f"Drives: {'; '.join(self.profile['drives'][:2])}",
            f"Strengths: {'; '.join(self.profile['strengths'][:2])}",
            f"Stories: {self.profile['stories'][0][:120]}",
            f"Tone: {self.style['tone']}",
            f"Rules: {'; '.join(self.style['rules'][:3])}",
        ]
        return "\n".join(lines)

    def qa_prompt_suffix(self, company, role):
        """Return a prompt fragment to append when generating QA answers."""
        return f"""
Candidate profile:
{self.compressed}

Answer the following question for {company} ({role}). Apply these rules:
- First person active voice
- Use a concrete example from the profile (adapt the matching story)
- Forward-looking framing — what you'll do for {company}, not what you want from them
- No cliches, no em-dashes, no apologetic language
- Keep it under 200 words
"""
