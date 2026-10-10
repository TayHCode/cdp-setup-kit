# Owner-run verification

Partial real-machine results from 2026-10-09 are recorded below. Use only a fresh disposable profile
and newly chosen port. Existing signed-in windows are never fixtures and
must not be closed for a check. Only an explicitly authorized disposable-machine test may run these checks.
Use `cdpkit-test-owner` with explicit port 9333+ in a fresh kit folder, or another disposable name
that cannot collide with existing setup.

- [ ] O1: On Windows, follow the README fresh setup. The visible window opens and `list` reports running in about ten minutes.
- [ ] O2: Preview and enable Windows startup from an ordinary account. Restart and sign in. Record any elevation refusal and any Chrome dialog; check that the window opens and endpoint answers without intervention.
- [ ] O3: Disable the Windows entry and remove the profile record. Only the marked task disappears and profile data stays.
- [ ] O4: Repeat setup, sign-out/sign-in, full restart and removal on Linux. Record desktop, keyring behavior and every dialog.
- [ ] O5: In the disposable profile, change a bookmark, site setting or throwaway sign-in. Confirm it survives a browser reopen and a machine restart.
- [ ] O6: Use an existing agent through Playwright and one MCP server. Attach to the existing context, open `https://example.com`, read its title, restart the browser and reconnect to the same HTTP endpoint.
- [ ] O7: With the disposable window closed, place a listener on its port. `open` exits 4 with a clear explanation and leaves the listener running.
- [ ] O8: Re-run `init` and `add` for the same name. Its port stays unchanged.
- [ ] O9: Connect from another machine through the documented SSH tunnel. The tunnel works and a direct attempt without it fails.
- [ ] O10: Run the opt-in Chrome test on Windows, Linux and macOS. Record the printed Browser string and whether the endpoint returned without interaction on both starts.
- [ ] O11: Have someone unfamiliar with the project follow the README without asking a question.

Run O10 only on a disposable desktop, with Google Chrome installed:

```sh
CDP_SETUP_KIT_REAL_CHROME=1 python3 -m unittest tests.test_real_chrome -v
```

On Windows set that variable in the terminal first, then run the Python
command. The test creates a new temporary folder, starts only its own Chrome
child, and ends that child during cleanup. It never reads existing config.
It checks `DevToolsActivePort` when present, exposure, a changed WebSocket path on restart,
and reuse of the same profile folder. It is skipped in the ordinary suite.

## macOS owner checklist

Checked over SSH on macOS 26.5.2 on 2026-10-09; login/reboot remain unverified. Use a new
disposable kit folder outside any checkout. Replace `KIT-DIR` below with its
absolute path, and keep `--kit-dir KIT-DIR` before every command. Use the new
profile `cdpkit-test-owner`, with no existing sign-ins. Confirm that its LaunchAgent
name is unused before enabling it. Leave everyday Chrome windows alone.

1. Run `python3 -m cdp_setup_kit --kit-dir KIT-DIR init --name cdpkit-test-owner --port 9333` in a Mac desktop terminal. Run `python3 -m cdp_setup_kit --kit-dir KIT-DIR list` and `python3 -m cdp_setup_kit --kit-dir KIT-DIR doctor cdpkit-test-owner`. Expect a visible window, an answering endpoint, a matching `DevToolsActivePort` if Chrome creates it (`running (endpoint answers)` when absent) and no exposure warning; record macOS and Chrome versions.
2. Add a disposable bookmark, close only this profile's windows and run `python3 -m cdp_setup_kit --kit-dir KIT-DIR open cdpkit-test-owner`. Confirm the bookmark survives. Use `python3 -m cdp_setup_kit --kit-dir KIT-DIR connect cdpkit-test-owner` to attach an existing agent to its existing context; reconnect to the same HTTP endpoint after reopening.
3. Preview `python3 -m cdp_setup_kit --kit-dir KIT-DIR startup enable cdpkit-test-owner`, then repeat with `--apply`. Check `plutil -lint "$HOME/Library/LaunchAgents/cdp-setup-kit-cdpkit-test-owner.plist"`. Sign out/in and then fully restart/sign in: expect the visible window, bookmark and answering endpoint each time (fixed-port Chrome reports `running (endpoint answers)`). Record every Login Items, Keychain or Chrome prompt and whether it required intervention.
4. Re-run `add cdpkit-test-owner` and confirm its port stays unchanged. With its window closed, put a small disposable listener on that port: `open cdpkit-test-owner` must exit 4 and leave the listener alone. Remove that listener yourself. Use `set-port cdpkit-test-owner 9334 --apply` with a free port: startup must become `stale`; preview and apply `startup enable cdpkit-test-owner` again, then check the new endpoint after sign-in. Try `add shop --profile-dir "~/Library/Application Support/Google/Chrome"`: expect exit 8 and no profile record. Use the same Python invocation and kit option for these commands.
5. Preview and apply `startup disable cdpkit-test-owner`, then `remove cdpkit-test-owner`, using the same kit option. Only the marked plist and profile record should disappear; data and unrelated entries must remain, and a loaded window must stay open. Close the disposable window yourself and sign in again: it must not reopen. A foreign same-name entry must be refused and kept.
6. Run `CDP_SETUP_KIT_REAL_CHROME=1 python3 -m unittest tests.test_real_chrome -v` from the checkout. This separately creates its own disposable profile. Record the Browser string, `DevToolsActivePort` presence or absence, loopback exposure check and successful restart with a new WebSocket path. Opt in only with explicit authorization for a disposable-machine check.

Graphical login/reboot, dialogs and real sign-in persistence remain unverified. Later headless Linux and startup-entry checks are recorded below; Linux visible-desktop startup remains unverified.

Update the recorded results and README status table only after observing the results.
O2, O4 or O10 failures require a fix before any real-machine claim. If Chrome
asks on every start, document that unattended reconnection is not available.

## Recorded partial verification — 2026-10-09

| Platform | Executed checks | Limits |
|---|---|---|
| macOS 26.5.2 / Chrome 154.0.8037.98 | Disposable init/open/list/doctor/connect, second profile, unchanged port on re-init/add, collision exit 4, default-folder refusal exit 8, stale-port update, foreign-plist refusal; startup preview/apply/status/disable/remove, plist lint and launchctl bootstrap/print/bootout; two-start Chrome test; Playwright and MCP via SSH tunnel before/after reopen; synthetic bookmark displayed after reopen | No visible-window/dialog observation, account sign-in, login trigger or reboot |
| Windows 11 build 26200 / Chrome 154.0.8037.99 | Same CLI safety/lifecycle checks, foreign-task refusal; task XML parse and schtasks registration/query/delete; two-start Chrome test; Playwright and MCP locally and through SSH tunnel before/after reopen; synthetic bookmark displayed after reopen | Initial task result 21 was fixed by granting the user access to new profile folders; manual task execution then answered CDP. SSH-launched Chrome ended when SSH closed. No graphical sign-in, dialogs or reboot |
| Ubuntu 26.04.1 LTS | Default-folder refusal, add/list/connect/remove and missing-Chrome diagnostics; Python 3.11 and 3.14 unit suites | Chrome absent, no desktop session; browser/startup/agent/keyring/reboot checks unverified |

O1 was partial (CDP launch checked; visible window unobserved). O3 and the
non-login portions of the Mac checklist were exercised with
explicit kit directories, disposable names and ports 9333/9334/9335, without
account sign-ins. O5 covered a synthetic bookmark changed locally while the
disposable browser was stopped and displayed after reopen, not restart of the
machine. O6/O7/O8/O9/O10 passed on the browser machines, with Windows client
checks requiring the SSH launcher session to remain open. Direct connections
to their test ports failed while SSH tunnels worked. Fixed-port Chrome omitted
`DevToolsActivePort` on both; the test now accepts that documented state while
checking its owned live child and endpoint. O2/O4/O11 remain unverified, as do
all reboot, logout/login, approval, Keychain/keyring and real sign-in persistence
checks. Windows task registration and execution failures were fixed and
re-tested with a fresh profile; Task Scheduler reported Running and CDP
answered. These results do not constitute owner approval of the final test
or publication.


## Session and headless fixes

Rechecked on 2026-10-10 with disposable profiles on newly selected unused ports:

- Windows SSH `init`/`open` refuse a visible launch; failed init leaves no profile record. The printed InteractiveToken task route answered CDP across SSH disconnect and browser reopen. The task and test browser were removed.
- macOS 26.5.2 with an existing GUI login: init/open, CDP title read, SSH disconnect, reopen and LaunchAgent preview/apply/disable/removal passed. Missing-GUI refusal is unit-tested; no graphical sign-in or reboot was performed.
- Linux system Chrome on Debian 13 and a no-admin Chrome for Testing ZIP on Ubuntu 26.04.1 LTS: explicit headless start, CDP title read, shell exit, reopen of the same profile folder, startup preview/apply/disable and cleanup passed. ZIP extraction required `chmod +x` for executable files. No Linux visible desktop or automatic startup was checked.
- No-Chrome Linux startup preview succeeds with an explicit provisional-path notice; applying enable refuses until Chrome is installed.

Live checks used raw CDP, not another Playwright/MCP installation. Earlier share/unshare and agent-client evidence remains above; Windows sharing was not applied again during this fix pass. Sign-ins, dialogs, graphical login triggers, reboot persistence, actual Linux apt/rpm installs and other CPU architectures remain unverified.
