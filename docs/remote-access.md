# Remote access

Chrome always listens on loopback. `share` prints an access plan and an agent
brief; no network/system changes happen without `--apply`; Windows preview saves a review script only. **CDP has no authentication.
Every program able to reach the address controls every tab, including signed-in
sites.** A peer address is not an agent identity. Never share profiles/cookies.
Changing provider data through an attached browser is a write requiring the
owner's authorization.

## Windows: a forward restricted to named peers

With an open kit profile, run this on the browser machine. Replace `BROWSER-IP`
and `PEER-IP` with the private IPv4 addresses of the browser and allowed peer.
Use the actual profile port printed by `connect` in every health check below:

```sh
cdp-setup-kit share main --to PEER-IP --address BROWSER-IP
cdp-setup-kit share main --to PEER-IP --address BROWSER-IP --apply
cdp-setup-kit share-status
cdp-setup-kit agent-brief main --write agent-brief.txt
```

Omit `--address` to discover `tailscale ip -4`; otherwise supply a numeric
local private IPv4 address. Repeat `--to PEER` for multiple named peers.
Private means RFC 1918 or Tailscale's shared address range, not arbitrary
non-global addresses. A numeric address also avoids Chrome's HTTP Host-header
restriction for remote machine names.

Read the short resource summary and saved PowerShell script before applying.
The preview prints its state-directory path, `Get-Content -LiteralPath` command
and SHA-256; `--show-script` prints the full script. Apply displays the same
hash and runs those exact in-memory bytes, refusing a changed saved copy.
`--apply` is consent to administrator changes. Open PowerShell with **Run as
administrator**, approve the UAC prompt, then rerun; there is no silent elevation.
An ordinary shell fails without creating resources. IP Helper must already run;
Windows Firewall must already be enabled with inbound default Block and local
rules allowed. The kit changes no services or default firewall policy.

Owned resources are:

- `netsh interface portproxy add v4tov4`: only `ADDRESS:PORT` to loopback at the same port. Never a wildcard listener or a different Chrome binding.
- Firewall allow rule `cdp-setup-kit-NAME`: TCP, that port, local address, selected interface, and the exact peer list.
- Companion block rule `cdp-setup-kit-NAME-deny`: the same port/address/interface, with every unlisted IPv4 address. This is required because existing broad allow rules, including private-network rules, can otherwise bypass a narrow allow rule. Block takes precedence. It does not affect other ports or addresses.
- Boot task `cdp-setup-kit-NAME-refresh`: SYSTEM, with a 30-second boot delay, running a protected script. It waits up to one minute for the recorded address on the same interface. It verifies ownership and firewall scope before restoring the proxy. It never starts Chrome or binds another address. The separate interactive Chrome task remains `cdp-setup-kit-NAME`.
- `%ProgramData%\cdp-setup-kit-shares\cdp-setup-kit-NAME\state.json` and `refresh.ps1`: administrator/SYSTEM writes only, ordinary users read only. Reparse points and writable/foreign ledgers are refused. The record identifies the kit config that owns the share; keep that config path stable.

An existing portproxy on the profile's port is refused even if it already
forwards to the right place. Existing named rules/tasks are refused without
the matching protected record. Reapplying identical settings verifies owned
resources and repairs missing ones. Changed address/peer settings require
unshare first. Changed existing owned rule/task/script/proxy contents are
refused, so an administrator's unfamiliar work is not overwritten.

A failure after the journal is written may leave a partial installation.
`share-status` reads the protected machine ledger, including partial entries
that never reached the user config. `unshare NAME --apply` can recover them
with the same kit config path. Inspect any reported drift before removing it.
Removal validates all resources first, stops/removes only the owned refresh
task, deletes only the exact proxy and two owned rules, and removes only the
owned files. It never recursively deletes unfamiliar contents.

From each allowed peer, run the brief's health check:

```sh
curl --fail --show-error --max-time 5 http://BROWSER-IP:9480/json/version
```

Expect HTTP 200 and Chrome version metadata. Run the same command from an
unlisted peer; expect refusal or timeout. `share-status` checks only from the
machine running it, so it does not prove peer restrictions. A later change to
firewall policy, addresses or administration can invalidate a previous test.

Remove and verify from the peers:

```sh
cdp-setup-kit unshare main
cdp-setup-kit unshare main --apply
cdp-setup-kit share-status
```

The direct address must stop answering, while Chrome's loopback endpoint can
remain running. Unshare before changing/removing a shared profile. Use the
installing version for unshare before upgrading: refresh script drift is
intentionally refused.

## macOS/Linux: an existing SSH tunnel

Run `share` on the browser machine with the same flags. It verifies the
browser-side loopback endpoint and prints the exact tunnel and health check
for each agent machine. `--apply` records instructions only; it installs no
SSH server, firewall policy, startup entry or direct forwarder. Direct
forwarding is unsupported because these systems have different firewall
policies that this kit cannot safely manage generically.

Follow the [README Remote access walkthrough](../README.md#remote-access).
On the intended agent machine, first check login interactively. For port 9480:

```sh
ssh USER@HOST true
ssh -N -L 9480:127.0.0.1:9480 USER@HOST
```

Verify the host-key fingerprint and answer `yes` once on first connection.
Numeric IPs and Host aliases can have separate known_hosts entries. For scripts
add `-o StrictHostKeyChecking=accept-new`: this automatically trusts an unseen
host (first-connection impersonation risk) but still refuses changed keys.
A throwaway `-o UserKnownHostsFile=TEMPFILE` tests clean trust without touching
your usual file; reuse it to test an existing entry.
If the default key fails, add `-i /path/to/key` and, if needed,
`-o IdentitiesOnly=yes`, or use your configured Host alias instead of USER@HOST.
For scripts also add `-o ExitOnForwardFailure=yes`.
In a second terminal, while the tunnel stays running:

```sh
curl --fail --show-error --max-time 5 http://127.0.0.1:9480/json/version
```

Keep the SSH session running while attached. The default local bind exposes
nothing on the agent machine's network interfaces. SSH authenticates an
account; `--to` is an intended-peer record, **not a source-address ACL**. Secure
the existing SSH server/account separately. Other programs on that agent
machine still control every tab through its local tunnel.

The generated brief uses the agent machine's loopback address. If its port
is occupied, change only the left/local port in `-L`, edit the port consistently in the generated brief. v0.2 has no separate local-port option. `unshare` deletes the
instruction record only; close each remote tunnel yourself. For containers,
create the tunnel inside the agent environment where its loopback is reachable.

## Agent brief

`agent-brief NAME [--address ADDRESS]` prints a block ready to paste into your
agents. `--write FILE` additionally writes a new file and refuses existing
files. Windows defaults to its recorded shared address; SSH defaults to
agent loopback. The block includes task-specific authorization, tab/profile
rules, a CDP security warning, both MCP client configs, and a health check
that never enumerates tabs. An explicit address override does not open access.

The snippets use an HTTP browser URL so the clients discover the current
WebSocket endpoint after a browser restart: Chrome DevTools MCP uses
[`--browser-url`](https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/configuration.md),
Playwright MCP uses [`--cdp-endpoint`](https://github.com/microsoft/playwright-mcp#configuration).
The examples pin Chrome DevTools MCP 1.10.1 and Playwright MCP 0.0.83.
Approve these versions or pin to a version you trust before installing.
These clients still need Node.js/npm and their own installation approval.
The kit neither downloads nor starts MCP servers.

## Verified steps and limits

Disposable-profile verification on 2026-10-09 used a newly selected unused port:

1. Windows 11: init/open, interactive Chrome task run, share preview/apply,
   idempotent apply, installed status, agent-brief file, and manual boot refresh
   task execution. Allowed private-network peer: HTTP 200. Two unlisted peers
   (Linux and macOS): HTTP 000, curl exit 28 after a five-second timeout.
2. Windows unshare preview/apply: shared endpoint no longer reachable; owned
   rules, proxy, refresh task and ledger removed. Existing unrelated browser
   ports still returned HTTP 200 and their rule/proxy snapshots matched before
   and after. The disposable Chrome task/profile/files were also cleaned up.
3. macOS 26.5.2 and Debian 13 Linux: init/open of disposable profiles, SSH share
   instructions, brief files, and tunnels from a Linux agent machine. Both
   tunnel `/json/version` checks returned HTTP 200; tunnels and test profiles
   were removed afterward.

Actual reboot/startup triggering, UAC dialog presentation, visible desktop
appearance, signed-in provider actions and live MCP consumption of the new
briefs remain unverified. No account data was inspected. Existing SSH
authentication was used; v0.2 does not provision SSH access. IPv6 and direct
macOS/Linux forwarding are unsupported. Wildcards, loopback, link-local,
multicast and reserved share addresses are always refused. Public/non-private
IPv4 requires the explicit dangerous
`--i-understand-this-exposes-signed-in-browsers` override and has no live
verification; avoid it. Source restrictions do not protect against a trusted
peer or local administrator, and they do not add CDP authentication.
