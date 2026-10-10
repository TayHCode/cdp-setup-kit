# Troubleshooting

Start with `cdp-setup-kit doctor`. PASS means that check succeeded; WARN asks
for attention; FAIL needs repair; INFO explains state. A failure exits 7.

## Unsupported platform

Use a Windows or macOS desktop, or Linux with a desktop or explicit headless mode. macOS support is unit-tested and
checked over SSH on macOS 26.5.2 on 2026-10-09; graphical sign-in and reboot
remain unverified. Follow the
[Mac owner checklist](verification.md#macos-owner-checklist) with a disposable profile.
Commands exit 9 on other systems; help and version still work.

## Chrome missing, unknown, or unable to start

Install Google Chrome yourself or provide `--chrome PATH` to `init` or `add`.
Check the path and execute permissions. Other Chromium browsers and snap or
flatpak wrappers are outside this version. An unknown version or identity
is a warning, not a launch block. Windows version detection does not run Chrome.
On macOS the default binary is
`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`.
For an installation elsewhere, pass the executable inside the app bundle to
`--chrome`, rather than the `.app` directory. Launches use that binary directly.

## Config invalid or from a newer version

Unreadable JSON is never overwritten. Repair it from `config.json.bak`
after inspecting both files. Use the newer tool for a newer schema. Names
must start with a lowercase letter, contain only lowercase letters, digits
and interior hyphens, and be at most 32 characters. Ports must be unique
integers from 1024 to 65535. Folders must be unique. Unknown keys are kept
but ignored; they cannot change Chrome's flags or listening address.

## Folder refused, missing, or readable by others

Use a dedicated folder outside everyday browser data, source checkouts,
shared storage and sync folders. Do not select an account folder or disk root.
Restore a missing parent or add a new profile. A missing profile folder is
created by `open`. On Linux and macOS restrict profile access to your own account.
Unsafe quoting characters in a browser or profile path are refused.
On Mac, `~/Library/Application Support/Google/Chrome`, its children and
ancestors are refused, including case variants and symlink aliases.

## Endpoint stopped

Run `cdp-setup-kit open NAME` from your desktop terminal. On Linux over SSH,
use `cdp-setup-kit open NAME --headless`. Windows SSH/session 0 launches are
refused: record with `init --yes --no-open --name NAME --port PORT`, then
`startup enable NAME --apply --force-no-desktop` and `startup run NAME --apply`
while that account is signed in to its desktop. macOS requires an existing
GUI login for the account. A failed init open does not record a new profile;
any retained browser folder is reported and left for your inspection. A stopped endpoint
does not mean the profile data was lost. `--no-wait` reports only that a
launch was requested, not that the endpoint works.

## Endpoint answers and profile evidence

A healthy endpoint shows `running (endpoint answers)`, with JSON status `running`.
Fixed-port/headless Chrome can omit `DevToolsActivePort`; absence is an INFO note,
not a warning. This proves CDP is available, not which profile owns an arbitrary
existing endpoint or whether an account is signed in. The tool will not open
another browser on that port. `running-unconfirmed` warns only when the marker
cannot be read; check folder permissions. A mismatching marker is a conflict:
inspect the listener and dedicated folder before using it.

## Port conflict or no free port

Close the other program yourself, or preview `cdp-setup-kit set-port NAME 9334`
with another port. Only `--apply` changes the record. Update a sign-in entry
separately. The tool never stops the existing listener or changes a port on
a setup re-run. Automatic selection tries 9222 through 9321; use an explicit
free port when that range is full.

## No desktop session

On Linux use a terminal in your desktop session, with `DISPLAY` or
`WAYLAND_DISPLAY`. Windows refuses SSH/session 0 and requires an interactive nonzero desktop
session; use the sign-in task while the account is logged in to its desktop.
On macOS use a terminal in the signed-in graphical session. A LaunchAgent
is limited to that session. Mac SSH launches answered CDP in the recorded
checks, but visible-window and dialog behavior was not observed.

## Chrome started but the endpoint did not answer

If Chrome ended at once or the profile looks open, it may already be running
without a debugging port. Close every window of that profile and run `open`
again. Look at the window and answer any question. A managed-device policy
may disable remote debugging. For a slow start use `--wait 60`.

## Startup disabled, stale, foreign, or refused

Disabled means there is no entry. Preview `startup enable NAME` if desired.
For stale entries run `startup enable NAME --apply` after reading the preview.
Foreign means a same-name entry lacks the marker; inspect it manually. The
tool will not overwrite it. A Windows registration refusal prints the exact
administrator command and points to [manual alternatives](startup.md).
Windows task XML uses the current security SID from a read-only `whoami`
query, rather than SSH environment account names. In the 2026-10-09 test,
an elevated SSH-created folder initially caused task result 21: Chrome could
not create its profile lock file. New kit-created Windows profile folders now
grant the current user SID inherited access; the least-privilege task run then
answered CDP. Existing/adopted folders keep their permissions. Inspect folder
access manually if an existing setup still fails; do not infer a successful
login trigger from `enabled`. Direct launches over SSH answered while that SSH session stayed
open and ended when it closed. Re-test from a graphical desktop terminal.

On Mac, inspect `~/Library/LaunchAgents/cdp-setup-kit-NAME.plist` and check
folder permissions when a write is refused. The preview contains the complete
plist. No `launchctl` command runs: enable and disable take effect at the next
graphical sign-in, and do not close a loaded browser. A symlink or malformed
plist is foreign and stays untouched. Startup status describes the file, not
whether launchd accepted it. If the next login opens no window, check macOS
Login Items approval, the Chrome binary path and any Keychain or browser dialog;
then use `open NAME` and `doctor`. Record the result in the owner checklist.

## Entry enabled but endpoint silent; Chrome asks again

Look at the window after sign-in. Answer anything Chrome asks, then run
`doctor`. If no window exists, use `open NAME`. With a dedicated folder and
the port switch, Chrome is not expected to ask for debugging permission,
but reboot behavior is not verified here. Chrome's newer switch-free route
from its inspect page does ask each session; a client's auto-connect option
may use that route. Use the explicit endpoint instead.

A power cut or forced restart may show a "restore pages" bubble. It is not
expected to block the port. Record actual dialogs in [verification](verification.md).
Linux automatic sign-in may leave the keyring locked and Chrome signed out.

## Exposure warning or unexpected WebSocket host

Inspect any port forward or proxy. Ensure it is intentional and restricted
to trusted agent machines. No detected non-loopback addresses means the
exposure probe was not checked, not that all network paths are safe.

## Works here, but not in the agent's container

Loopback belongs to the machine or container where the client runs. Use
[an SSH tunnel](remote-access.md) from that environment. Do not broaden Chrome's
listening address. If `localhost` fails, use `127.0.0.1` in client settings.

## Data deletion refused or test mode

Deletion requires a kit-created direct folder with no link, a stopped
endpoint and no open-profile hint. Close the window first. An adopted folder
must be removed by hand if you really no longer need it. `refused: test mode`
means the development guard blocked a real action; use fakes for tests.
On Mac even a stale `SingletonLock` makes automatic deletion refuse. Use
ordinary `remove --apply` to retain the data, then inspect it manually after
closing every window of that disposable profile.
