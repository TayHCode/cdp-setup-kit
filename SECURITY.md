# Security

```text
SECURITY NOTICE
A Chrome window opened by this tool has a debugging port. Any program that
can reach that port can read and control every tab in that window, including
every site you are signed in to there. There is no password on the port.
Sign in only to the accounts you want your agents to use. The port listens on
this computer only. Do not forward it to a network you do not control.
```

CDP has no authentication. Loopback is not per-user: every signed-in account
and local program can reach it. Do not use this on a shared machine.

Since Chrome 136, debugging switches are ignored on Chrome's default data
folder. The change limits cookie theft from everyday profiles. This tool
requires a dedicated folder and refuses known everyday browser locations.
See [Chrome's explanation](https://developer.chrome.com/blog/remote-debugging-port).

A profile folder holds live sign-ins. Treat it as secret. Never place it in
a synced folder, shared backup or repository, or copy it to another machine.
Sign in manually to only the accounts you want your agents to use.

Never use 0.0.0.0 or `--remote-allow-origins=*` to expose Chrome.
The tool always uses loopback and has no option for extra Chrome flags.
For remote access, use an existing SSH tunnel or explicit Windows `share`.
Windows sharing leaves Chrome on loopback and adds an exact-address portproxy,
scoped allow rule and scoped block rule for all unlisted IPv4 peers. It requires
explicit `--apply` administrator consent after printing the exact commands.
Direct forwarding on macOS/Linux is unsupported. Read [remote access](docs/remote-access.md).

Inside a profile folder, the tool reads only `DevToolsActivePort`, the
`SingletonLock` link, and the presence of `lockfile`. It does not read
cookies, saved logins, history or preferences. It does not copy, export or
sync profile data. The only HTTP discovery request is `/json/version`; it never
lists tabs or drives a page. Only an applied stop opens a browser WebSocket,
solely to send `Browser.close` after verifying ownership.

The tool never kills processes; stop asks Chrome to close its own kit window.
`stop NAME` previews first; `--apply` verifies the loopback listening process's
executable and exact kit launch arguments, including the recorded user-data-dir,
before sending DevTools `Browser.close` on its browser WebSocket. It never
enumerates tabs or reads browsing data. Unverifiable ownership is refused.
The endpoint must disappear before stopped is reported; all tabs/windows in that
dedicated profile close, so coordinate with agents first. Profile data remains. Unshare stops only its owned boot refresh task. Sign-in entries are previewed before apply;
only entries carrying its marker can be changed or removed. The Windows
preview includes a conditional ownership check because it runs no scheduler
command until apply. Foreign entries are left untouched.

An attached agent acts with your signed-in permissions. Sites may limit or
close accounts for automated activity. This launcher grants no permission
to act on any site. The agent and its actions remain your responsibility.

No usage statistics, update checks or downloads.
Network work is limited to endpoint metadata checks, local exposure probes and
the verified browser-close request; share-status can check the configured private address.
The exposure probe warns if the port answers through another address of
this machine. Review any intentional forward and its access restrictions.

Report problems through the repository's private vulnerability report
feature when available. Do not post sign-in data or full profile folders.
