# Daily rewards browser workflow

## Intent

Extend the existing Playwright session launcher to perform the requested daily
wheel and shop gift workflow for `WonderfulFinch83`.

## Approach

Use Playwright to operate the website, with its normal signing and cookie
handling. Observe the website's API responses to confirm identity, reward
availability, and successful claims. This fits the requested browser workflow
and avoids reproducing claim API calls. Direct API automation would require
additional implementation of reward actions; coordinate-based clicking would
be sensitive to window size and offer changes.

## Sequence

1. Load existing session cookies and open the website.
2. Require a successful profile response and an exact match to
   `WonderfulFinch83`, also checking the displayed username. On mismatch or
   missing identity, stop before any reward action.
3. Navigate to Benefits using its link. Dismiss recognized informational and
   promotional pop-ups using their close controls. Stop on an unknown blocking
   pop-up rather than selecting an arbitrary button.
4. Scroll the Daily Wheel section into view. If a reset countdown is present,
   record it and skip. Otherwise require the site's `FreeSpinAvailable` flag
   and a zero-cost available wheel before clicking the free spin control.
   Confirm the successful claim response and resulting cooldown/unavailability.
5. Dismiss recognized result pop-ups, then navigate to Shop.
6. Locate the daily gift card in the standard offer carousel and move to the
   last card. Require `FreeGiftAvailable` and the matching free claim control.
   Skip when a cooldown is shown. Confirm a successful claim response and
   resulting cooldown/unavailability.
7. Dismiss recognized result pop-ups and print a result for each reward:
   claimed, skipped with cooldown, or failed. Leave the browser open for review
   until Enter is pressed.

## Constraints and failure behavior

- Do not select paid offers, spend loyalty points, or claim other free offers.
- Never infer availability solely from the absence of a countdown.
- Never automatically repeat a claim click after an ambiguous timeout; it may
  already have succeeded. Stop and inspect instead.
- Save a local screenshot on unexpected page states. Treat screenshots as
  private account data and exclude them from version control.
- Retain the current session loader; session renewal remains unproven.

## Evidence and validation

The open browser displays the expected username. Benefits currently shows
`Resets in 20h 43m`; the last standard shop card shows `Available in 20h 42m`.
The HAR includes `FreeSpinAvailable`, zero-cost wheel metadata,
`FreeGiftAvailable`, and profile `Name`/`DisplayName` fields.

Test identity mismatch, cooldown skips, free availability checks, and failures
without making real claims. Verify the current cooldown workflow in the browser.
The available-to-claim path needs a live check when the rewards next become
available; fixture coverage alone will not establish that live path works.
