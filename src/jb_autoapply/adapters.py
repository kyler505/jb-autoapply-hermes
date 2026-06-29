from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import nopecha as _nopecha
from . import simplify as _simplify
from . import accounts as _accounts


@dataclass
class ApplyPlan:
    site: str
    url: str
    steps: list[str]
    blockers: list[str]
    submit_boundary: str
    review_checks: list[str]
    browser_profile: dict[str, Any]
    manual_checkpoints: list[dict[str, str]]
    nopecha_enabled: bool = False
    simplify_enabled: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            'site': self.site,
            'url': self.url,
            'steps': self.steps,
            'blockers': self.blockers,
            'submit_boundary': self.submit_boundary,
            'review_checks': self.review_checks,
            'browser_profile': self.browser_profile,
            'manual_checkpoints': self.manual_checkpoints,
            'nopecha_enabled': self.nopecha_enabled,
            'simplify_enabled': self.simplify_enabled,
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
        has_acct = _accounts.has_account(str(job.get('url', '')))
        if has_acct:
            steps += [
                'If needed, click Apply / Apply Manually',
                'Expect multi-step wizard; re-read form state after each step',
                'If a sign-in page appears -> sign in with stored credentials',
                'No account creation needed — reuse existing account',
            ]
        else:
            steps += [
                'If needed, click Apply / Apply Manually',
                'Expect multi-step wizard; re-read form state after each step',
                'If a sign-in or create-account page appears:',
                '  1. Check for "Sign in with Google" first (preferred)',
                '  2. If not available, create account with email (kcao@tamu.edu) + generated password',
                '  3. Save account to ~/.hermes/ats_accounts.json for reuse',
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
    nopecha_ready = _nopecha.is_ready()
    simplify_ready = _simplify.is_ready()
    browser_profile: dict[str, Any] = {
        'mode': 'assisted',
        'nopecha_enabled': nopecha_ready,
        'simplify_enabled': simplify_ready,
        'action_delay_ms': {'min': 350, 'max': 1200},
        'post_action_settle_ms': 900,
        'post_upload_settle_ms': 1500,
        'per_step_rescan': True,
        'input_strategy': [
            'Prefer native clicks, keyboard entry, and visible controls only',
            'Avoid hidden-field writes or bypass-style DOM mutation',
            'Re-read the page after uploads, save-and-continue actions, and validation errors',
        ],
    }

    if simplify_ready:
        browser_profile['input_strategy'].append(
            'Simplify Copilot extension is loaded — it auto-detects ATS forms '
            'and auto-fills fields from the stored profile. Wait for it to finish '
            'before interacting with the form.',
        )

    if nopecha_ready and simplify_ready:
        # Both extensions: load both, skip --disable-extensions-except
        browser_profile['extension_args'] = _simplify.playwright_args_with_nopecha()
        browser_profile['challenge_signals'] = []
    elif nopecha_ready:
        browser_profile['challenge_signals'] = [
            # NopeCHA handles these automatically — no manual stop needed
        ]
        browser_profile['nopecha_args'] = _nopecha.playwright_args()
    else:
        browser_profile['input_strategy'].append(
            'Stop immediately when challenge text or anti-bot UI appears',
        )
        browser_profile['challenge_signals'] = [
            'captcha',
            'recaptcha',
            'hcaptcha',
            'verify you are human',
            'unusual traffic',
            'security check',
        ]

    manual_checkpoints: list[dict[str, str]] = []
    if not nopecha_ready:
        manual_checkpoints.append({
            'kind': 'challenge',
            'trigger': 'Any CAPTCHA, anti-bot, unusual-traffic, or security-check prompt',
            'action': 'Pause, capture screenshot/state, mark manual_required, and wait for the user to complete the prompt',
        })
    manual_checkpoints += [
        {
            'kind': 'verification',
            'trigger': 'Any email OTP, SMS code, account-creation password, or identity-verification boundary',
            'action': 'Pause and request the user to complete the verification step before resuming',
        },
        {
            'kind': 'final-review',
            'trigger': 'Final review screen before submit',
            'action': 'Present the completed application summary and wait for explicit human approval before submit',
        },
    ]
    review_checks = [
        'Role title matches posting',
        "Company-specific 'why us' text is specific",
        'Resume attached is the intended variant',
        'Work authorization / sponsorship answer is correct',
        'No unresolved placeholders remain',
    ]
    return ApplyPlan(
        site=site,
        url=str(job.get('url', '')),
        steps=steps,
        blockers=blockers.get(site, blockers['generic']),
        submit_boundary='Manual review only; explicit human approval required before submit',
        review_checks=review_checks,
        browser_profile=browser_profile,
        manual_checkpoints=manual_checkpoints,
        nopecha_enabled=nopecha_ready,
        simplify_enabled=simplify_ready,
    )
