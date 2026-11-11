# Session capture and import

The worker reuses two authentication cookies from a successful game-opened website session. It does not generate fast-login links or guarantee renewal of expired sessions. HAR files include private credentials; keep them local, restrict access, and never commit or attach them to an issue.

## Capture on iOS using a Mac

1. On the iOS device, enable Safari's **Web Inspector** under Safari's Advanced settings (on newer iOS, Safari settings are under Settings → Apps). On the Mac, enable Safari's developer features in Safari Settings → Advanced. Exact labels vary by OS version; see [WebKit's enabling instructions](https://webkit.org/web-inspector/enabling-web-inspector/).
2. Connect the unlocked device using a cable, accept the device trust prompts, and keep it unlocked. On the Mac select Safari's Develop → your device → the inspectable MONOPOLY GO page. [Apple explains connected-device inspection](https://developer.apple.com/documentation/safari-developer-tools/inspecting-ios).
3. Open the Network tab. Enable preservation of navigation history if available. Use the game's website link to produce a fresh successful authenticated launch while the inspector is recording. Keep the request history through redirects.
4. Confirm the expected username appears on the website. Find a successful GET request to `api.prod.monopolygo.com/web-portal/user-profile`; the capture needs both authentication cookies on that request. A desktop page that merely loads while logged out is insufficient.
5. Export the network table as a HAR using Export or Command-S with Network focused. These export mechanisms are documented in [WebKit's Network reference](https://webkit.org/web-inspector/network-tab/). Protect the saved file, for example `chmod 600 /path/to/successful-session.har`.

If Export is disabled, confirm the Network table contains requests recorded for the currently attached page and the device remains connected. Capture new activity with the inspector attached, then try export again. Do not rely on replaying an old fast-login URL. This project's successful capture was made on iOS; current Safari UI variations and disabled-export recovery have not all been independently verified. If the game does not expose an inspectable page, that is an app/OS limitation; this project cannot force inspection on.

## Import locally

Stop the worker before importing. From the configured project directory:

```sh
uv run monopolygo-rewards import-session --har /path/to/successful-session.har
uv run monopolygo-rewards --login-only
```

Import is offline and does not require the JavaScript signing bundle. It saves only the allowed authentication cookies in Mozilla cookie format, at `DATA_DIR/SESSION_FILE` (default `data/session.cookies`). It does not copy the HAR into runtime data. Existing `.monopoly-session.cookies` is compatible: copy it to that path and set permissions to 600. Set `--state /absolute/path/to/cookies` if migrating without copying.

## Import through Docker

Create `.env` and the writable runtime directories as in [setup](setup.md). Build the image, stop any running worker, then mount only the capture needed for import:

```sh
docker compose stop rewards
docker compose run --rm -v /absolute/path/to/successful-session.har:/capture.har:ro rewards import-session --har /capture.har
docker compose run --rm rewards --login-only
docker compose up -d
```

The container UID10001 must be able to read the capture. To preserve owner-only permissions, a Linux host can copy the capture to a private temporary directory owned by UID10001, import it, then remove that temporary copy. Avoid loosening the permissions on the original HAR.

## Expiry and replacement

When rejected credentials or a username mismatch is detected, no claims occur; scheduled mode performs identity-only checks every `AUTH_RETRY_INTERVAL`. Capture a new authenticated session, stop the worker, import it, and restart. To check immediately regardless of saved schedule, run `--login-only` or `--once` while the worker is stopped. Each browser run reloads the session file and saves legitimate cookie updates only after identity verification.

Two cookie names are required: `X-WithBuddies-Cookie-SessionToken` and `X-WithBuddies-Cookie-SessionToken-Domain`. The `SessionToken-Domain` marker may legitimately be an empty string; it must still be present. The actual `SessionToken` must be nonempty. Do not put their values in `.env` or logs. No expiry in the file does not mean the server will accept the session forever.
