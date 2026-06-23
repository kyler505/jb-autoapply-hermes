from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ApplyPlan:
    site: str
    url: str
    steps: list[str]
    blockers: list[str]
    submit_boundary: str
    review_checks: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            'site': self.site,
            'url': self.url,
            'steps': self.steps,
            'blockers': self.blockers,
            'submit_boundary': self.submit_boundary,
            'review_checks': self.review_checks,
        }


def detect_site(url: str) -> str:
    u = (url or '').lower()
    if 'myworkdayjobs.com' in u or 'workday.com' in u:
        return 'workday'
    if 'ashbyhq.com' in u:
        return 'ashby'
    if 'greenhouse.io' in u:
        return 'greenhouse'
    if 'lever.co' in u:
        return 'lever'
    if 'icims.com' in u:
        return 'icims'
    if 'smartrecruiters.com' in u:
        return 'smartrecruiters'
    if 'oraclecloud.com' in u:
        return 'oracle'
    if 'successfactors.com' in u:
        return 'successfactors'
    return 'generic'


def build_plan(job: dict[str, Any]) -> ApplyPlan:
    site = detect_site(str(job.get('url', '')))
    steps = [
        'Open the application URL',
        'Attach the prepared resume PDF',
        'Fill autofill fields from the packet',
        'Fill screening answers from the Q&A bank',
        'Resolve any visible {{placeholders}} only from facts in the vault',
        'Stop at the review boundary and wait for human approval',
    ]
    if site == 'workday':
        steps += [
            'If needed, click Apply / Apply Manually',
            'Expect multi-step wizard; re-read form state after each step',
            'Never create an account or enter a password; stop at that boundary',
        ]
    elif site == 'ashby':
        steps += [
            'Upload resume first before typing free-text fields',
            'Re-check required fields after upload because the form may re-render',
        ]
    elif site == 'greenhouse':
        steps += ['Use keyboard selection for typeahead and native selects']
    elif site == 'lever':
        steps += ['Fill text inputs before moving to the next section']
    elif site == 'icims':
        steps += ['Treat repeated sections as independent; duplicate questions happen']
    elif site == 'smartrecruiters':
        steps += ['Prefer keyboard selection over programmatic select changes']
    elif site == 'oracle':
        steps += ['Watch for nested step flows and strict required fields']
    elif site == 'successfactors':
        steps += ['Treat candidate profile and application as separate validation scopes']
    else:
        steps += ['Use the review checklist and stop if any required field is ambiguous']

    blockers = {
        'workday': ['account creation required before submit'],
        'ashby': ['resume upload triggers re-render'],
        'greenhouse': ['email verification or OTP may require manual step'],
        'lever': ['site-specific anti-bot checks can require manual intervention'],
        'generic': ['any unresolved placeholder or required field'],
    }
    review_checks = [
        'Role title matches posting',
        "Company-specific 'why us' text is specific",
        'Resume attached is the intended variant',
        'Work authorization / sponsorship answer is correct',
        'No unresolved placeholders remain',
    ]
    return ApplyPlan(site=site, url=str(job.get('url', '')), steps=steps, blockers=blockers.get(site, blockers['generic']), submit_boundary='Manual review only; user clicks submit', review_checks=review_checks)
