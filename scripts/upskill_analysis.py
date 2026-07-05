"""Weekly upskill gap analysis — reads today's queue and outputs learning plan context."""

import sys
import os
from collections import Counter

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from jb_autoapply.selector import build_queue


def pick_top_competitive(queue: list[dict], n: int = 3) -> list[dict]:
    """Pick the top N competitive/technical roles from the queue."""
    keyword_signals = [
        "software engineer", "swe", "full stack", "backend", "frontend",
        "ml engineer", "ai engineer", "data engineer", "devops",
        "infrastructure", "platform engineer", "systems engineer",
        "site reliability", "security engineer",
    ]
    scored = []
    for job in queue:
        role = (job.get("role") or "").lower()
        company = (job.get("company") or "")
        url = job.get("url") or ""
        score = 0
        for kw in keyword_signals:
            if kw in role:
                score += 2
        # Penalize non-technical
        if "manager" in role and "product" not in role:
            score -= 1
        if "sales" in role or "marketing" in role:
            score -= 2
        if score >= 2:
            scored.append((score, job))

    scored.sort(key=lambda x: -x[0])
    return [job for _, job in scored[:n]]


def main() -> str:
    """Read queue, pick top competitive jobs, return a self-contained prompt."""
    queue = build_queue()
    if not queue:
        return "No jobs in queue for upskill analysis."

    top = pick_top_competitive(queue, n=3)
    if not top:
        return "No competitive/technical roles found in queue for upskill analysis."

    lines = []
    lines.append("# 🔬 Weekly Upskill Gap Analysis")
    lines.append(f"Found {len(top)} technical role(s) in today's queue:\n")
    for i, job in enumerate(top, 1):
        co = job.get("company", "?")
        ro = job.get("role", "?")
        url = job.get("url", "")
        lines.append(f"### {i}. {co} — {ro}")
        lines.append(f"   URL: {url}")
        lines.append("")

    # Collect cross-job skill demands
    all_titles = [j.get("role", "") for j in top]
    companies = [j.get("company", "") for j in top]
    lines.append(f"**Companies:** {', '.join(companies)}")
    lines.append(f"**Roles:** {', '.join(all_titles)}")
    lines.append("")

    lines.append("## Candidate Profile (Kyler Cao)")
    lines.append("- Texas A&M CS+Business 2027, Cypress TX")
    lines.append("- Current: Product & Engineering Intern @ Global Shop Solutions (ERP software)")
    lines.append("- Stack: Python, ML/AI (scikit-learn), React/Next.js, Playwright, Git, Linux")
    lines.append("- Automation pipelines, full-stack web dev, browser automation")
    lines.append("- US citizen, no sponsorship needed")
    lines.append("")

    lines.append("## Task")
    lines.append(
        "For each job above:\n"
        "1. Fetch the job posting URL and extract required/preferred skills\n"
        "2. Diff against Kyler's profile to identify hard skill gaps\n"
        "3. Synthesize domain/tooling gaps\n"
        "4. Build a prioritized gap heatmap (Critical / High / Medium / Low)\n"
        "5. Web-search study resources for the top 2-3 gaps\n"
        "6. Produce a learning plan with estimated time per gap\n\n"
        "Output format: markdown report with heatmap table, study resources, and recommended study order."
    )

    return "\n".join(lines)


if __name__ == "__main__":
    output = main()
    print(output)
