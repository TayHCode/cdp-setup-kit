# cdp-setup-kit

## What this does

Open separate Chrome windows, sign in by hand, and keep their browser data
between starts. Each named window has a stable local Chrome DevTools Protocol
(CDP) address. `share` makes that address reachable by agents over your private network;
`agent-brief` gives them ready-to-paste instructions and MCP settings for
working in the existing signed-in context.

Requires Python 3.9+ and either installed Google Chrome for local profiles or a
reachable existing CDP HTTP endpoint. `--no-open` skips launching Chrome; local
setup still requires Chrome. The kit never downloads Chrome. For an existing
browser, use [endpoint setup](#what-you-need). Otherwise choose your platform
from the supplied checkout. No pip, venv or packages are needed:

**Windows desktop** — [desktop quickstart](#quickstart-windows)
Use `py` on Windows; `python3` may be the Microsoft Store stub and is not required.
```powershell
cd cdp-setup-kit
py -m cdp_setup_kit init --name main --port 9333
py -m cdp_setup_kit connect main
```
Windows: [from a remote shell](#quickstart-windows), record with `--yes --no-open` first; prepare the desktop sign-in task explicitly.
**macOS desktop** — [desktop quickstart](#quickstart-macos)
```sh
cd cdp-setup-kit
python3 -m cdp_setup_kit init --name main --port 9333
python3 -m cdp_setup_kit connect main
```
macOS: [from a remote shell](#quickstart-macos), use `--yes --no-open`; opening needs this account signed in at the desktop.
**Linux desktop** — [desktop quickstart](#quickstart-linux)
```sh
cd cdp-setup-kit
python3 -m cdp_setup_kit init --name main --port 9333
python3 -m cdp_setup_kit connect main
```
Linux: [without a desktop](#quickstart-linux), use `init --yes --no-open`, then `open main --headless`.
Accept the notice, then sign in manually in the dedicated window. On a shared
or throwaway machine, put `--kit-dir DIR` before every command, with a new folder
outside the checkout, and choose an unused port. See [Remote access](#remote-access)
for a tunnel from another agent machine.

## Security notice

```text
SECURITY NOTICE
A Chrome window opened by this tool has a debugging port. Any program that
can reach that port can read and control every tab in that window, including
every site you are signed in to there. There is no password on the port.
Sign in only to the accounts you want your agents to use. The port listens on
this computer only. Do not forward it to a network you do not control.
```

Read [SECURITY.md](SECURITY.md) before using a signed-in account.

## Status

Version 0.2.0. Real-machine checks use disposable profiles and newly selected ports.

| System | Verified operations | Startup entry | Sharing | Login/reboot persistence |
|---|---|---|---|---|
| Windows | Setup/open/list/doctor/connect and port conflict on a real machine; interactive task from SSH | Preview/apply/run/removal checked; login trigger unverified | Live share/unshare with a peer allow-list and allowed/unlisted peer checks | **not yet checked** |
| Linux | Headless setup/open/list/doctor/connect and SSH tunnel on real machines | Preview/apply/disable checked; graphical sign-in **not yet checked** | SSH tunnel checked; direct forwarding unsupported | **not yet checked** |
| macOS | Setup/open/list/doctor/connect and port conflict on a real machine over SSH | Preview/apply/load/removal checked; login trigger unverified | SSH tunnel checked; direct forwarding unsupported | **not yet checked** |

Verified on 2026-10-09 and rechecked on 2026-10-10: macOS 26.5.2 (25F84), Chrome 154.0.8037.98;
Windows 11 build 26200, Chrome 154.0.8037.99; Ubuntu 26.04.1 LTS
(Chrome for Testing headless); Debian 13, Chrome 155.0.8059.39 (system Chrome headless and SSH tunnel).
Playwright and Playwright MCP attached to existing contexts on both browser
machines, including after browser reopen and through SSH tunnels. Synthetic
bookmarks survived reopen. Fixed-port Chrome omitted `DevToolsActivePort`;
the endpoint still answered. A responding endpoint now shows **running (endpoint answers)**.
The JSON status is `running`; this means CDP answers, not that any account is signed in
or that the profile identity is proven. A matching folder marker provides extra evidence.
An absent marker is an INFO note only. `running-unconfirmed` means CDP answers but
the marker could not be read (WARN: check folder permissions). `stopped` means
no endpoint answers; with an enabled sign-in entry, doctor warns that it is not
answering. `conflict` means a non-CDP listener or a mismatching folder marker
(FAIL: inspect the listener/profile); `not-checked` means probes were skipped.
Windows direct share/unshare, manual boot refresh, unchanged unrelated browser
rules, and allowed/unlisted peer checks passed with a disposable profile.
macOS and Debian SSH tunnels returned HTTP 200 from an agent machine.
All three platforms are unit-tested with a fake launcher, fake scheduler,
and fake CDP server.
Visible windows/dialogs, account sign-ins, sign-out/in, reboot persistence,
and unattended reconnection remain unverified. The [owner checks](docs/verification.md)
record these limits; scheduler registration alone does not verify sign-in start.

## What you need

For local profiles, install Google Chrome and Python 3.9 or newer on Windows 10,
Windows 11, Linux, or macOS. A desktop session is needed for visible
windows; SSH alone cannot supply one. Chrome is never downloaded by this tool.
Google Chrome for Testing is also supported via `--chrome PATH`; other Chromium
browsers, snap and flatpak are unsupported.
The quickstarts run directly from a clone and need no packages.

With an existing CDP HTTP endpoint, Chrome does not need to be installed on this
machine. Validate the endpoint and print connection settings:

```sh
python3 -m cdp_setup_kit init --yes --no-open --endpoint http://127.0.0.1:9333
```

On Windows replace `python3` with `py`. Supply the browser's HTTP origin, with
no path, credentials, query, or fragment. HTTPS and WebSocket URLs are not
supported by this probe. A failed connection or non-CDP response exits 5.
Endpoint setup does not record a managed profile, launch a browser, or change
startup entries. Keep the printed address for your client; local profile commands
such as `open`, `connect NAME`, and `startup` do not manage this external browser.
Use only an owner-authorized endpoint on a trusted network or tunnel. Do not
combine `--endpoint` with `--name`, `--port`, or `--chrome`.


Optional command installation: run `pipx install .`, or create a virtual
environment and run `python3 -m pip install .` inside it (`python` also works when available). Do not install into
the system Python. Then `cdp-setup-kit` is the command name used below.
This version is not on a package index. On Debian/Ubuntu,
creating a venv may require `sudo apt install python3-venv`. Running from the
checkout needs no venv or pip.

**Supplied Git bundle: start with this clone command.** A bundle may have no
default HEAD, so select its `main` branch explicitly:

```sh
git clone --branch main SUPPLIED-BUNDLE cdp-setup-kit
```

Then `cd cdp-setup-kit` and use the Python commands below. A supplied checkout/archive
needs no clone. After publication, clone the intended public destination with:

```sh
git clone https://github.com/TayHCode/cdp-setup-kit.git
```

For any supplied or published checkout, continue with:

```sh
cd cdp-setup-kit
    # Recommended: run directly, even without python3-venv or pip.
python3 -m cdp_setup_kit --kit-dir ../cdp-kit-quickstart list --no-check
    # Or, if uv is already installed:
uv run --no-project --python 3.11 python3 -m cdp_setup_kit --kit-dir ../cdp-kit-quickstart list --no-check
    # Optional installation only (Debian/Ubuntu may need python3-venv first):
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install .
```

Run the test suite from the checkout (one process at a time):

```sh
python3 -B -m unittest discover -s tests -t . -q
```

## Install Chrome on Linux

For x86_64 Debian/Ubuntu, in a new download folder:

```sh
curl -fLO https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && sudo apt install ./google-chrome-stable_current_amd64.deb
```

For x86_64 Fedora/RHEL-compatible systems:

```sh
curl -fLO https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.rpm && sudo dnf install ./google-chrome-stable_current_x86_64.rpm
```

These system installs need administrator rights and may add Google's update
repository. See [Google's installation requirements](https://support.google.com/chrome/answer/95346).
The kit itself never installs Chrome. Without admin rights, download Chrome for
Testing into a new folder you own (this pinned linux64 example was checked):

```sh
mkdir -m 700 chrome-for-testing-download
cd chrome-for-testing-download
curl -fLO https://storage.googleapis.com/chrome-for-testing-public/155.0.8059.39/linux64/chrome-linux64.zip
python3 -m zipfile -e chrome-linux64.zip .
chmod +x chrome-linux64/chrome chrome-linux64/chrome_crashpad_handler chrome-linux64/chrome_sandbox
./chrome-linux64/chrome --version
```

Python ZIP extraction does not preserve executable permissions; the `chmod`
step is required. Do not make `chrome_sandbox` setuid or disable the sandbox.
Run as a regular user. Chrome still needs OS shared libraries and sandbox
support; a minimal server may require an administrator to install missing
libraries. Get a current archive for your architecture from the official
[Chrome for Testing availability page](https://googlechromelabs.github.io/chrome-for-testing/).
Use its absolute `chrome` path with `init --chrome PATH` or `add NAME --chrome PATH`.

## Quickstart (Windows)

1. Clone `https://github.com/TayHCode/cdp-setup-kit.git` after publication, or get the supplied checkout/archive; `cd cdp-setup-kit` in a desktop terminal with Python installed.
2. Run `py -m cdp_setup_kit init --name main --port 9333`; accept the notice.
3. Sign in to your chosen accounts in the window that opens.
4. Run `py -m cdp_setup_kit connect main`; copy the printed HTTP endpoint into your agent.
5. Run `py -m cdp_setup_kit startup enable main`; read the preview.
6. Run `py -m cdp_setup_kit startup enable main --apply` to enable sign-in start.
7. After a future restart and sign-in, run `py -m cdp_setup_kit list`; the login trigger still needs your check.
8. Add another window: `py -m cdp_setup_kit add research --port 9334`, then `py -m cdp_setup_kit open research`.

Over SSH or in session 0, `init`/`open` refuse a visible launch with exit 5.
A direct SSH launch would be tied to that shell. With this account already
signed in to the desktop, use the kit's InteractiveToken task instead:

```powershell
py -m cdp_setup_kit init --yes --no-open --name main --port 9333
py -m cdp_setup_kit startup enable main
py -m cdp_setup_kit startup enable main --apply --force-no-desktop
py -m cdp_setup_kit startup run main --apply
py -m cdp_setup_kit connect main
py -m cdp_setup_kit list
```

This shell has no desktop session (it is a remote/SSH or service session): a visible window cannot open from here. The machine can still have an active desktop.
The shipped InteractiveToken task runs on that account's desktop and survives the SSH shell ending.
`startup run` reports `already running` when IgnoreNew would ignore another start.
Close your own profile first with `py -m cdp_setup_kit stop main --apply` before restarting.
The manual equivalent is `schtasks /Run /TN cdp-setup-kit-main`; its SUCCESS means only an attempted run, even if already running.
It cannot create a graphical login. Details: [sign-in entries](docs/startup.md).

## Quickstart (Linux)

1. Clone `https://github.com/TayHCode/cdp-setup-kit.git` after publication, or get the supplied checkout/archive; `cd cdp-setup-kit`. Install Chrome using the steps above.
2. In a desktop terminal, run `python3 -m cdp_setup_kit init --name main --port 9333`; accept the notice.
3. Sign in to your chosen accounts in the window that opens.
4. Run `python3 -m cdp_setup_kit connect main`; copy the printed HTTP endpoint into your agent.
5. Run `python3 -m cdp_setup_kit startup enable main`; read the preview.
6. Run `python3 -m cdp_setup_kit startup enable main --apply` to enable graphical sign-in start.
7. After a future restart and sign-in, run `python3 -m cdp_setup_kit list`; desktop autostart still needs your check.
8. Add another window: `python3 -m cdp_setup_kit add research --port 9334`, then `python3 -m cdp_setup_kit open research`.

With neither `DISPLAY` nor `WAYLAND_DISPLAY`, visible launches refuse with
exit 5. A sign-in entry only runs at graphical sign-in, not inside SSH.
For an SSH-only server, use [Chrome Headless](https://developer.chrome.com/docs/automation-and-testing/headless):

```sh
python3 -m cdp_setup_kit init --yes --no-open --name main --port 9333
python3 -m cdp_setup_kit open main --headless
python3 -m cdp_setup_kit list
python3 -m cdp_setup_kit doctor main
python3 -m cdp_setup_kit connect main
python3 -m cdp_setup_kit agent-brief main
curl --fail http://127.0.0.1:9333/json/version
```

For Chrome for Testing, add `--chrome /absolute/path/to/chrome` to `init`.
Headless mode keeps the dedicated profile and exposes CDP without a window;
manual sign-in needs a desktop. It stays running after the SSH shell exits,
but there is no headless boot/sign-in entry. `startup enable` always launches
a visible window. Without a detected desktop session its preview warns clearly,
and applying refuses unless you explicitly add `--force-no-desktop` to prepare
for a future graphical sign-in. This override does not supply a desktop or
make a headless startup entry. To close this kit browser, preview
`python3 -m cdp_setup_kit stop main`, then run `python3 -m cdp_setup_kit stop main --apply`.
The tool never kills processes; stop asks Chrome to close its own kit window through CDP `Browser.close`.

## Quickstart (macOS)

1. Clone `https://github.com/TayHCode/cdp-setup-kit.git` after publication, or get the supplied checkout/archive; `cd cdp-setup-kit` in a Mac desktop terminal.
2. Run `python3 -m cdp_setup_kit init --name main --port 9333`; accept the notice.
3. Sign in to your chosen accounts in the window that opens.
4. Run `python3 -m cdp_setup_kit connect main`; copy the printed HTTP endpoint into your agent.
5. Run `python3 -m cdp_setup_kit startup enable main`; read the LaunchAgent preview.
6. Run `python3 -m cdp_setup_kit startup enable main --apply` to enable graphical sign-in start.
7. After a future restart and sign-in, run `python3 -m cdp_setup_kit list`; record any approval or Keychain dialog.
8. Add another window: `python3 -m cdp_setup_kit add research --port 9334`, then `python3 -m cdp_setup_kit open research`.

Chrome is discovered at `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`.
In a non-interactive SSH shell, use both `--yes --no-open` to record first:

```sh
python3 -m cdp_setup_kit init --yes --no-open --name main --port 9333
python3 -m cdp_setup_kit open main
python3 -m cdp_setup_kit connect main
```

`open` creates a visible window on this account's logged-in desktop, even when
called over SSH. It can launch only when this account already has a GUI session;
without one, `init`/`open` refuse with exit 5. Sign in to the Mac desktop and
run from its terminal. The LaunchAgent takes effect at the next graphical
sign-in. First use a disposable profile for the [Mac owner checklist](docs/verification.md#macos-owner-checklist).

## Commands

From the checkout, check the command without opening Chrome or installing
anything. This lists an empty disposable kit and needs no Chrome installation.

```sh
python3 -m cdp_setup_kit --kit-dir ../cdp-kit-quickstart list --no-check
```

| Command | Purpose |
|---|---|
| `init` | The one-line result comes first (interactive consent questions precede it); notice and snippets follow. `--quiet --yes` prints only the result. Repeating an existing setup says nothing changed; `--notice` prints the notice again. Guided setup; `--yes` accepts the notice and defaults; `--no-open` records without opening and prints the name, port and folder. A failed requested open never records a new profile; retained browser folders are reported. |
| `add NAME` | Record a profile; optional `--port`, `--profile-dir`, `--chrome`. Does not open it. |
| `open NAME` | Open a visible window, or Linux headless Chrome with `--headless`; `--wait SECONDS` defaults to 20; `--no-wait` skips polling. |
| `stop NAME` | Preview graceful close of every window/tab in this dedicated profile; `--apply` sends DevTools `Browser.close` only after the recorded loopback listener's executable and user-data-dir match the kit launch arguments. Reports stopped only after the endpoint disappears. Refuses unverifiable ownership; never forces a process to exit. |
| `list` | List endpoints; `--json` gives one object; `--no-check` skips CDP probes. |
| `doctor [NAME]` | Explain setup problems; `--json` gives structured checks. |
| `startup status [NAME]` | Show disabled, enabled, stale or foreign entries; supports `--json`. |
| `startup run NAME` | Windows: preview running the owned interactive task; `--apply` starts it or reports already running. The account needs an active desktop. |
| `startup enable NAME` | Preview visible sign-in start even without Chrome (shows a provisional path); `--apply` requires Chrome. No detected desktop session prints a warning and requires explicit `--force-no-desktop` to apply for a future graphical sign-in. |
| `startup disable NAME` | Preview removal of a marked entry; `--apply` makes the changes. |
| `connect NAME` | Attach help; `--client` selects a client, `--ws` fetches the current address, `--json` gives metadata. |
| `share NAME --to PEER` | Preview named-peer access; optional repeated `--to`, `--address`, `--apply`; Windows `--show-script` prints the saved script. |
| `unshare NAME` | Preview removal of owned sharing entries; `--apply` removes them; Windows `--show-script` prints the saved script. |
| `share-status` | Inspect shares and probe CDP; run peer checks separately. |
| `agent-brief NAME` | Pasteable agent rules/MCP settings; optional `--address`, `--write FILE`. |
| `set-port NAME PORT` | Preview a port change; `--apply` records it. Update a startup entry separately. |
| `remove NAME` | Preview removal; `--apply` keeps profile data unless eligible `--delete-data` is also given. |

Use `--kit-dir DIR` before the command for portable config, profiles and state.
`CDP_SETUP_KIT_DIR` does the same; the command option wins. Neither changes
the sign-in entry location. `CDP_SETUP_KIT_CHROME` selects an installed binary
unless the config or `--chrome` already selects one. There is no extra-flags option.
Re-running `add` never changes an established port. Use `set-port` explicitly.

Without `--name`, first `init` uses `main`; with existing profiles its default
new name is empty, so it adds nothing. Without `--port`, `init` and `add` scan
**9222 through 9321 inclusive, ascending**, choosing the first port not
recorded for another profile in this kit, whose CDP probe gets connection
refused and which has no accepting IPv4 loopback listener. Thus an empty kit with no
listeners selects **9222**; existing listeners and recorded ports are skipped.
No free candidate means exit 4. This is a point-in-time check, not a reservation;
`open` checks again and refuses a conflict without stopping its owner.

Examples use explicit **9333/9334** to avoid the commonly occupied default
range. Choose an unused port from 1024 through 65535 with `--port`, e.g.
`cdp-setup-kit add research --port 9334`. An explicit port recorded for another
profile is refused; an explicit busy port is recorded with a warning so you
can prepare configuration, but `open` refuses until free. Separate kit folders
do not share allocations. Always use the endpoint printed for your profile.

Exit codes (also usable from scripts):

| Code | Meaning |
|---|---|
| 0 | Success, including unchanged setup or preview. |
| 1 | File/system failure, timeout, ended input or internal error. |
| 2 | Invalid command/input or missing interactive consent. |
| 3 | Invalid config, unknown profile or sharing record mismatch. |
| 4 | No free candidate, or an accepting listener prevents opening. |
| 5 | Chrome unavailable, launch failed, or no desktop session without the explicit override. |
| 6 | Sign-in entry refusal or registration failure. |
| 7 | Doctor found a FAIL check. |
| 8 | Safety refusal (folder, sharing, script or output destination). |
| 9 | Unsupported platform. |
| 10 | Requested port is already recorded for another profile. |

## Connect an agent

Give the agent `http://127.0.0.1:9333`, the HTTP endpoint from `connect`.
It stays stable; the browser WebSocket address changes after each start.
Attach to the existing context (`browser.contexts()[0]` in Node.js) to use
the window's sign-ins. [Examples and MCP settings](docs/connect-agents.md).

## Use it from another machine

Windows can share one endpoint with named private-network peers. macOS and
Linux print an SSH tunnel for the agent machine. Follow [remote access](docs/remote-access.md).

TIME-WAIT connections after a stop do not count as a listener and need no port
change. `open` probes a TCP connection rather than treating a failed bind as busy.

## Remote access

For macOS/Linux, use an existing SSH account on the browser machine. This
walkthrough was checked from a Linux agent to disposable macOS and Linux
windows, with both empty and existing host-key files. Substitute your profile
name, port, browser host and SSH user throughout. On the browser machine:

```sh
python3 -m cdp_setup_kit init --yes --no-open --name main --port 9333
python3 -m cdp_setup_kit open main
python3 -m cdp_setup_kit share main --to PEER-IP --address BROWSER-IP --apply
```

On an SSH-only Linux browser machine add `--headless` to `open`; for Chrome for
Testing add `--chrome /absolute/path/to/chrome` to `init`. On the agent machine,
first check SSH login interactively, then keep the tunnel running:

```sh
ssh USER@HOST true
ssh -N -L 9333:127.0.0.1:9333 USER@HOST
```

First connection asks to trust the host key: verify its fingerprint with the
host owner and answer `yes` once **in an interactive terminal**. Without a terminal,
an unknown host fails with `Host key verification failed`. The non-interactive
alternative beside that step is:

```sh
ssh -o StrictHostKeyChecking=accept-new USER@HOST true
ssh -N -o StrictHostKeyChecking=accept-new -o ExitOnForwardFailure=yes -L 9333:127.0.0.1:9333 USER@HOST
```

This automatically trusts the first key (verify the host through another trusted
channel first), and still refuses changed keys. An already trusted Host alias may have a
separate entry from the numeric IP; use that alias or verify the new entry.
For scripts add `-o StrictHostKeyChecking=accept-new`: it trusts unseen hosts
automatically (risk of impersonation on first connection), but refuses changed
keys. To test without changing your usual trust database, add
`-o UserKnownHostsFile=TEMPFILE` with a new throwaway path; repeat with the same
file to test an existing trusted entry. Never disable changed-key checks.

If login says `Permission denied`, use `-i /path/to/key` (and
`-o IdentitiesOnly=yes` if needed), or replace `USER@HOST` with the Host alias
that already chooses the correct user/key in your SSH config. Use the same
identity for both commands. Add `-o ExitOnForwardFailure=yes` for scripts to
fail immediately if the local port cannot be forwarded. The default SSH local
forward binds only loopback; do not add `-g` or a wildcard bind.

In a second terminal on the agent machine:

```sh
curl --fail --show-error --max-time 5 http://127.0.0.1:9333/json/version
```

Expect HTTP 200 and Chrome metadata. Give the agent this local HTTP address
and the `agent-brief` from the browser machine; for SSH it includes the tunnel
command. A preview says **PREVIEW: not live yet**. Keep the tunnel terminal
open while attached; use Ctrl-C to close your tunnel. `unshare main --apply`
removes only the instruction record and cannot stop a tunnel on another machine.
SSH must already be configured; `--to` records intended peers, not a source ACL.
See [the full walkthrough and Windows route](docs/remote-access.md).

## Share with your agents

**CDP has no authentication. Every program able to reach the address controls
every tab, including signed-in sites.** Peer restrictions identify machines,
not individual agents or programs. Keep Chrome on loopback and sign in manually
only to accounts authorized for the task.

Replace `BROWSER-IP` and `PEER-IP` with the private IPv4 addresses of your browser and permitted agent machines. Run `init`
and `open` first, then on the browser machine:

```sh
cdp-setup-kit share main --to PEER-IP --address BROWSER-IP
cdp-setup-kit share main --to PEER-IP --address BROWSER-IP --apply
cdp-setup-kit share-status
cdp-setup-kit agent-brief main
cdp-setup-kit agent-brief main --write agent-brief.txt
cdp-setup-kit unshare main
cdp-setup-kit unshare main --apply
```

`--address` defaults to `tailscale ip -4` when installed. Otherwise provide a
numeric private IPv4 address. Repeat `--to` for each permitted peer address.
Both preview and apply print a short plan and agent brief. Windows saves the
full script under the kit state directory and prints its path, a Get-Content
command, line count and SHA-256. Add `--show-script` to print it. Apply executes the same
script bytes whose hash is displayed; it refuses a modified saved copy.
Preview's brief says **PREVIEW: not live yet** and grants no access.

On **Windows**, apply requires an elevated PowerShell: choose **Run as
administrator**, approve UAC, then rerun with `--apply`. The kit never elevates
silently. It adds an exact-address portproxy to loopback, an allow rule named
`cdp-setup-kit-NAME`, a companion `-deny` rule for unlisted IPv4 peers (so broad
existing allow rules cannot bypass the list), and a `-refresh` task at boot.
Firewall rules also bind to the selected interface. The protected ownership
ledger/script live in `%ProgramData%\cdp-setup-kit-shares`; moving `--kit-dir`
does not move them. Existing entries are never adopted or overwritten.

On **macOS/Linux**, run the printed SSH command on each agent machine, replace
`USER` with an existing SSH account, and keep it running. The local bind
uses SSH's loopback default. Give agents the printed loopback brief. `--apply`
records instructions only; it installs no server or direct forwarder. `--to`
is an intended-peer list, not an SSH source-address ACL. Access is controlled
by your existing SSH server/account. Verify the printed `curl` health check
on the agent machine. `unshare` forgets instructions; close tunnels yourself.

The brief includes the task authorization, tab/profile rules, HTTP-based
Chrome DevTools MCP and Playwright MCP configuration, and `/json/version`
health check. `--write` refuses an existing file. Details and verified steps
are in [remote access](docs/remote-access.md).

## Where things are stored

| Item | Windows | Linux | macOS |
|---|---|---|---|
| Config | `%APPDATA%\cdp-setup-kit\config.json` | `$XDG_CONFIG_HOME/cdp-setup-kit/config.json`, default `~/.config/cdp-setup-kit/config.json` | `~/Library/Application Support/cdp-setup-kit/config.json` |
| Profiles | `%LOCALAPPDATA%\cdp-setup-kit\profiles\NAME` | `$XDG_DATA_HOME/cdp-setup-kit/profiles/NAME`, default `~/.local/share/cdp-setup-kit/profiles/NAME` | `~/Library/Application Support/cdp-setup-kit/profiles/NAME` |
| State | `%LOCALAPPDATA%\cdp-setup-kit\state` | `$XDG_STATE_HOME/cdp-setup-kit`, default `~/.local/state/cdp-setup-kit` | `~/Library/Application Support/cdp-setup-kit/state` |
| Sign-in entry | Scheduled task `cdp-setup-kit-NAME` | `$XDG_CONFIG_HOME/autostart/cdp-setup-kit-NAME.desktop`, default `~/.config/autostart/cdp-setup-kit-NAME.desktop` | `~/Library/LaunchAgents/cdp-setup-kit-NAME.plist` |

With `--kit-dir DIR`, these become `DIR/config.json`, `DIR/profiles/`, and
`DIR/state/`; the sign-in entry stays in the OS location. Config rewrites
keep a `config.json.bak`. The tool keeps no log. Profile folders contain
live sign-ins; keep them outside source checkouts, shared storage and sync tools.

## Optional: closing idle tabs

See the [separate companion note](docs/idle-tabs.md). This tool installs no timer.

## Limitations

- Windows and macOS desktops; Linux desktops or explicit headless mode. Real-machine coverage is limited to the checks above. Google Chrome and Chrome for Testing only; no other Chromium browsers, snap or flatpak packages.
- Keeping the folder does not promise permanent sign-in. Sites expire sessions and may tie them to a device. You will sometimes sign in again.
- Windows open at sign-in, not power-on. A signed-in desktop is required.
- Common Linux desktops honour autostart; some minimal window managers ignore it. Automatic sign-in can leave the desktop keyring locked, prompting Chrome or making it appear signed out.
- Windows 11 registration and manual task execution worked for an ordinary logged-in account. Task registration may be refused for an ordinary account and need the displayed administrator command. Registration and manual task execution passed after fixing new-profile permissions; interactive sign-in start remains unverified. Direct SSH launches ended with the SSH session; they are now refused before starting. Use the interactive task route above.
- Mac startup changes apply at the next graphical sign-in; a loaded window stays open when its plist is removed. macOS may require login-item approval or show a Keychain dialog; record this in the owner checks.
- A forced restart may leave a "restore pages" bubble. Look at the window if the endpoint stays silent.
- The tool never kills processes; `stop NAME --apply` asks Chrome to close its own kit window. It verifies the recorded loopback listener's executable and user-data-dir first, using /proc on Linux, lsof/ps on macOS, or PowerShell on Windows. Unavailable process information causes refusal; close the window at its desktop instead. It cannot tell which agent is using it. Profile data and sign-in entries stay in place; close waits up to ten seconds for the endpoint to disappear.
- The port has no password. Any account or program on the computer can reach it. Avoid shared computers.
- Windows direct sharing requires existing IP Helper service and enabled Windows Firewall with inbound default Block. The kit changes neither services nor default policy. Direct forwarding on macOS/Linux is unsupported; existing SSH access is required.
- Sharing is IPv4 only. Wildcard, loopback, link-local, multicast, IPv6 and reserved addresses are refused. Public/non-private addresses are refused unless `--i-understand-this-exposes-signed-in-browsers` is explicitly given; this dangerous override never permits a wildcard bind.
- Peer addresses can change. Unshare, verify identities, then share again with the updated addresses; no automatic address widening or migration. Unshare before changing a shared profile port or removing it.
- Local share-status checks cannot prove allowed/denied peer access. Windows installation, idempotent apply, manual refresh, peer isolation and removal were tested; actual reboot refresh, UAC dialogs and visual desktop appearance remain unverified. Administrators can override firewall/ownership protections; local programs retain loopback access.
- Boot refresh restores the selected address only when it exists on its recorded interface. It does not start Chrome; an interactive sign-in is still required. Unshare a Windows share using the version that installed it before upgrading, because refresh script drift is refused.
- This version is not on any package index. Playwright and Playwright MCP attach behavior was checked; other clients remain unverified.

## Remove it

For each profile, preview and then apply:

```sh
cdp-setup-kit unshare NAME
cdp-setup-kit unshare NAME --apply
cdp-setup-kit startup disable NAME
cdp-setup-kit startup disable NAME --apply
cdp-setup-kit stop NAME
cdp-setup-kit stop NAME --apply
cdp-setup-kit remove NAME
cdp-setup-kit remove NAME --apply
```

The profile folder and config backup remain after stop and remove.
Delete retained folders by hand only after checking the displayed paths and
deciding you no longer need the sign-ins. `remove --delete-data --apply`
can delete only a stopped, direct profile folder created by this kit.
Uninstall the optional command with the package manager used to install it.

## License

[MIT](LICENSE), copyright TayHCode.
