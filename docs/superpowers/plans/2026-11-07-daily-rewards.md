# Daily Rewards Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task by task.

**Goal:** Verify WonderfulFinch83 and claim only the available daily free wheel and shop gift.

**Architecture:** Keep cookie loading in `script.py`. Add `daily_rewards.py` for
API observation, identity checks, guarded browser actions, and failure artifacts.
Use the website's existing test IDs and normal request signing.

**Tech Stack:** Python, Playwright sync API, unittest.

**Spec:** `docs/superpowers/specs/2026-11-07-daily-rewards-design.md` (approved).

**Execution status:** Implemented and reviewed. See
`2026-11-07-daily-rewards-progress.md` for verification evidence and limits;
the steps below preserve the original plan.

## Global Constraints

- No paid offers or loyalty point spending.
- No availability inference solely from an absent countdown.
- No automatic retries of ambiguous claim clicks.
- Unknown blocking states stop the workflow and save a private screenshot.
- Leave the browser open until Enter; preserve login-only use through an option.

## Review Focus

- Identity missing/mismatched: no reward action.
- Malformed/failed availability response: no claim.
- Timer/API disagreement: skip on timer, otherwise fail closed.
- Duplicate/hidden controls: target only one visible daily control.
- Claim timeout or failure: stop without retrying; no false claimed result.

### Task 1: Identity and reward decisions

**Files:** create `daily_rewards.py`, `test_daily_rewards.py`.
**Interfaces:** `verify_identity(payload, expected)`; `free_wheel_key(data)`;
`gift_available(data)`; these functions reject incomplete state.

- [ ] Write tests for username success/mismatch/missing data and free/paid/unknown availability.
- [ ] Run `.venv/bin/python -m unittest discover`; expect failures for missing functions.
- [ ] Implement validation against the captured API's PascalCase fields.
- [ ] Run the suite; expect all tests pass.

### Task 2: Browser workflow and launcher

**Files:** modify `script.py`, `daily_rewards.py`, `.gitignore`, `SESSION_PROBE.md`;
extend `test_daily_rewards.py`.
**Interfaces:** `DailyRewards(page, expected).run()` consumes Task 1 validators;
`observe(response)` is attached before navigation to collect API state.

- [ ] Write fixture browser tests for cooldown skip, free claims, blocked pop-ups,
  malformed availability, username mismatch, and failed/ambiguous claim responses.
- [ ] Run those tests; expect missing workflow failure.
- [ ] Implement Benefits navigation, scoped pop-up dismissal, zero-cost wheel
  selection, last daily gift card scrolling, single claim clicks, and confirmation.
- [ ] Wire username argument/default and login-only option into `script.py`;
  save screenshots on failures and keep browser open for inspection.
- [ ] Run full unittest suite; expect all tests pass, with live browser checks
  separately reported if the environment blocks Chromium.
- [ ] Document commands, result statuses, and live-claim verification limits.

## Execution notes

This workspace is not a Git repository, so worktree/commit review scripts do not
apply. Implement in place as authorized. Shared interface: Task 2 consumes the
three Task 1 validators; no conflicts. User approval includes implementation;
no further execution-method approval is needed.
