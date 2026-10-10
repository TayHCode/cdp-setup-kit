# Open at sign-in

Windows uses a per-user scheduled task named `cdp-setup-kit-NAME` in the
root task folder. Linux uses a desktop autostart file named
`cdp-setup-kit-NAME.desktop`. macOS uses a per-user LaunchAgent named
`cdp-setup-kit-NAME.plist`. All three start Chrome directly, with the recorded
folder and port; Python and the source checkout are not part of the entry.
Moving the tool does not break it. Chrome must still be installed at that path. Previews work without Chrome and
label the displayed path provisional; applying enable requires an installed binary.
These entries always start visible Chrome, including on Linux; `open --headless`
is an explicit manual route with no startup entry.

```sh
cdp-setup-kit startup enable NAME
cdp-setup-kit startup enable NAME --apply
cdp-setup-kit startup status NAME
cdp-setup-kit startup disable NAME
cdp-setup-kit startup disable NAME --apply
```

Read the complete file and commands in the preview. Without `--apply`, no
file is changed and no scheduler command runs. Windows previews show an
ownership query plus conditional create commands: `/F` is used only for
a marked, stale task. Apply queries before any write and refuses a foreign
entry. A current entry is unchanged. Disabling an absent entry is harmless.
Status commands query Windows but do not change tasks.

Use Task Scheduler to inspect the Windows task. The current security SID is
read with `whoami` even during preview, without changing any task. New Windows
profile folders grant that SID inherited access so an elevated setup shell
does not block the least-privilege task; existing folders retain their ACLs.
It uses the current account's
ordinary interactive token at that account's sign-in; it has no time limit
and ignores an overlapping launch. No administrator rights are requested.
If registration fails, use the exact administrator command printed by the
tool once, or use the manual shortcut below. Registration and XML encoding
remain subject to the [owner's checks](verification.md).

On Linux, inspect `~/.config/autostart/` or `$XDG_CONFIG_HOME/autostart/`.
Only a file with the kit's marker is changed. Common desktops honour this
folder; some minimal window managers do not. Entries run after sign-in,
never before anyone signs in. Automatic sign-in can leave a keyring locked.

On macOS, inspect `~/Library/LaunchAgents/cdp-setup-kit-NAME.plist`. Its
`ProgramArguments` array keeps each argument separate, including paths with
spaces. `RunAtLoad` starts it at graphical sign-in (`Aqua`); `KeepAlive` is
false, so closing Chrome does not cause a restart. The file is written
atomically with mode `0600`. The marker, label and profile must identify the
kit's entry before it can be replaced or removed; links and malformed files
are foreign. A changed port or Chrome path makes the entry stale.

Enable and disable only write or remove that plist. They run no `launchctl`
command, take effect at the next graphical sign-in, and leave existing Chrome
windows open. Status describes the installed file, not a loaded launchd job.
To try the browser immediately, use `open NAME`. After changing a port, close
that profile's windows yourself before reopening. If macOS asks for Login
Items approval or Chrome asks about Keychain access, inspect the request and
record it in the [Mac owner checklist](verification.md#macos-owner-checklist).
The plist lint and load were checked on macOS 26.5.2 on 2026-10-09.
Actual graphical sign-in and reboot remain unverified.

To reopen a closed window:

```sh
cdp-setup-kit open NAME
```

On Windows, preview `cdp-setup-kit startup run NAME`, then add `--apply` to
run the shipped interactive task. It reports `already running` when IgnoreNew
prevents an overlapping start. The manual `schtasks /Run /TN cdp-setup-kit-NAME`
may print SUCCESS even when no new instance started.
This shell has no desktop session (it is a remote/SSH or service session): a visible window cannot open from here.
Run at the desktop or use this task with the same account signed in there.
Preview `cdp-setup-kit stop NAME`, then add `--apply` before restarting the task.

After `set-port NAME PORT --apply`, update the entry with
`startup enable NAME --apply`; the port change alone leaves the entry stale.
If you adopted a folder that already has a manually created sign-in entry,
remove that old entry by hand after inspecting it. The tool does not search
for or alter unrelated tasks.

## Manual Windows alternative

The tool does not install this alternative. Create a shortcut in your own
Startup folder using the desktop's Startup-folder controls. Copy and edit
this target with a dedicated folder and the port recorded in the config:

```text
"C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="D:\kit-data\profiles\work" --remote-debugging-port=9333 --no-first-run --no-default-browser-check
```

Inspect its endpoint with `doctor`. Remove the shortcut manually to undo it.
Do not also enable the kit task for the same folder.

## Manual Linux alternative

For a session that ignores desktop autostart, this is a copy-and-edit
systemd user unit. The tool never writes, installs or enables it. Follow your
desktop's guidance for importing the graphical session environment first.

```ini
[Unit]
Description=Open a dedicated Chrome window at graphical sign-in
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=exec
ExecStart=/opt/google/chrome/chrome --user-data-dir=/srv/kit-data/profiles/work --remote-debugging-port=9333 --no-first-run --no-default-browser-check

[Install]
WantedBy=graphical-session.target
```

Use a dedicated writable folder and the config's port. Choose either this
manual unit or desktop autostart, then check with `doctor`. Remove any manual
unit yourself; the tool only manages its marked desktop file.

When no desktop session is detected (Linux without DISPLAY/WAYLAND_DISPLAY,
Windows session 0/remote shell, or macOS without this account's GUI session),
`startup enable` warns that a visible window cannot open here. `--apply` refuses
unless you add `--force-no-desktop` explicitly to prepare for a future graphical
sign-in. Prefer running at the desktop; on Linux use `open NAME --headless` for
an immediate headless browser. Disabling an entry needs no desktop session.
