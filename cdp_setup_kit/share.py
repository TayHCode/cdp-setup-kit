"""Explicit sharing plans; Chrome itself always stays on loopback."""
import hashlib
import ipaddress
import json
from typing import Optional

from . import config
from .constants import APP_NAME, LOOPBACK, DEVTOOLS_MCP, PLAYWRIGHT_MCP
from .errors import KitError
from .profiles import get_profile
from .paths import path_module

# RFC 1918: 10/8, 172.16/12, 192.168/16; Tailscale shared range: 100.64/10.
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(value) for value in (
    (0xa000000, 8), (0xac100000, 12), (0xc0a80000, 16), (0x64400000, 10)))


def address(value: str, scary: bool = False, loopback: bool = False) -> str:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        raise KitError(2, "use a numeric IPv4 address, not a host name or CIDR") from None
    if ip.version != 4 or ip.is_unspecified or ip.is_multicast or ip.is_reserved or ip.is_link_local or (ip.is_loopback and not loopback):
        raise KitError(2, "refused: wildcard, loopback, IPv6, multicast, reserved or link-local address")
    if not (loopback and ip.is_loopback) and not any(ip in network for network in PRIVATE_NETWORKS) and not scary:
        raise KitError(2, "refused: address is not private or Tailscale", "public access requires --i-understand-this-exposes-signed-in-browsers")
    return str(ip)


def choose_address(system, requested: Optional[str], scary: bool = False) -> str:
    if requested:
        return address(requested, scary)
    binary = system.which("tailscale")
    if binary:
        code, out, _ = system.run([binary, "ip", "-4"])
        values = out.strip().splitlines()
        if code == 0 and len(values) == 1:
            candidate = address(values[0])
            if ipaddress.ip_address(candidate) in PRIVATE_NETWORKS[-1]:
                return candidate
    raise KitError(2, "no Tailscale IPv4 address found; give --address PRIVATE-IP")


def validate_shares(data) -> None:
    shares = data.get("shares", {})
    if not isinstance(shares, dict):
        raise KitError(3, "invalid sharing records")
    for name, record in shares.items():
        config.validate_name(name)
        if not isinstance(record, dict) or record.get("mode") not in {"windows", "ssh"}:
            raise KitError(3, "invalid sharing record: " + name)
        config.validate_port(record.get("port"), 3)
        address(record.get("address", ""), scary=True)
        peers = record.get("peers")
        if not isinstance(peers, list) or not peers:
            raise KitError(3, "invalid sharing peers: " + name)
        for peer in peers:
            address(peer, scary=True)
        if type(record.get("scary", False)) is not bool:
            raise KitError(3, "invalid sharing consent")


def brief(name: str, port: int, host: str, available: bool = True) -> str:
    url = "http://{}:{}".format(host, port)
    intro = ("A Chrome browser window (dedicated profile " + name + ") is available at " if available else "PREVIEW: not live yet. After applying and verifying access, a Chrome browser window (dedicated profile " + name + ") will be available at ") + url + "; sign in to the accounts you want agents to use."
    snippets = {"mcpServers": {
        "chrome-devtools": {"command": "npx", "args": ["-y", DEVTOOLS_MCP, "--browser-url=" + url]},
        "playwright": {"command": "npx", "args": ["-y", PLAYWRIGHT_MCP, "--cdp-endpoint", url]},
    }}
    return '\n'.join([intro,
        'Use it for the owner-authorized task for profile "' + name + '"; sign-ins must be authorized for that task.',
        'Rules: do not close other windows/tabs you did not open; never copy or export profiles/cookies; changing provider data through it is a write.',
        'Attach to the existing browser context. Do not create a signed-out replacement context.',
        'WARNING: CDP has no authentication. Every program able to reach the address controls every tab, including signed-in sites.',
        'The owner signs in manually; availability does not prove any account is signed in.',
        '\nMCP examples are pinned; approve these versions or pin to a version you trust before installing.',
        'MCP client configuration (HTTP browserURL form; clients discover the current WebSocket URL):',
        json.dumps(snippets, indent=2), '\nHealth check (does not enumerate tabs):',
        'curl --fail --show-error --max-time 5 ' + url + '/json/version'])


def agent_brief(system, data, name, requested=None, write=None) -> None:
    profile = get_profile(data, name)
    record = data.get("shares", {}).get(name)
    host = address(requested, scary=bool(record and record.get("scary")), loopback=True) if requested else record["address"] if record and record["mode"] == "windows" else LOOPBACK
    if record and record["port"] != profile["port"]:
        raise KitError(3, "sharing port differs from profile; unshare before changing it")
    output = brief(name, profile["port"], host, system.cdp_at(host, profile["port"])["kind"] == "valid")
    if record and record["mode"] == "ssh":
        output += "\n\nOn the agent machine, keep this SSH tunnel running:\n" + ssh_command(record["address"], profile["port"]) + "\n" + SSH_NOTE
    elif host != LOOPBACK or not record:
        output += "\n\nFor access over SSH, on the agent machine keep this tunnel running instead of connecting directly:\n" + ssh_command(host if host != LOOPBACK else "HOST", profile["port"]) + "\nUse the browser machine's SSH host for HOST, and connect to " + endpoint_url(profile["port"]) + " through the tunnel.\n" + SSH_NOTE
    if write:
        destination = system.resolve_path(write)
        if system.exists(destination):
            raise KitError(8, "refused: --write destination already exists")
        system.write_text(destination, output + "\n")
    print(output)


SSH_NOTE = ("First connection asks to trust the host key: verify it and answer yes once, or run ssh USER@HOST true interactively first. "
            "For scripts add -o StrictHostKeyChecking=accept-new: this trusts an unseen host automatically (first-connection impersonation risk), but refuses changed keys. "
            "If you use a key add -i KEY (and -o IdentitiesOnly=yes if needed), or use your Host alias from SSH config instead of USER@HOST.")


def ssh_command(host: str, port: int) -> str:
    return 'ssh -N -L {}:{}:{} USER@{}'.format(port, LOOPBACK, port, host)


def endpoint_url(port: int) -> str:
    return "http://{}:{}".format(LOOPBACK, port)


def _windows(system, paths, name, record, action, show_script=False):
    from .share_windows import script
    content = script(name, record, paths.config, action)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    destination = path_module(system).join(paths.state, action + "-" + name + "-" + digest + ".ps1")
    if system.is_link(destination):
        raise KitError(8, "refused linked preview script; inspect it before retrying")
    if system.exists(destination):
        if system.read_text(destination) != content:
            raise KitError(8, "refused changed preview script; inspect it before retrying")
    else:
        system.write_text(destination, content)
    print("Full script saved: " + destination)
    print("Read in PowerShell: Get-Content -LiteralPath '" + "''".join(destination.split("'")) + "'")
    print("Script lines: {}. Rerun with --show-script to inspect the full script. Script SHA256: {}".format(len(content.splitlines()), digest))
    if show_script:
        print(content)
    # Execute the same in-memory bytes whose hash was displayed, never load a
    # user-writable script after elevation (which would allow a file-swap race).
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", content]


def change(system, paths, data, name, peers, requested=None, apply=False, scary=False, show_script=False):
    profile = get_profile(data, name)
    selected = choose_address(system, requested, scary)
    allowed = sorted({address(peer, scary) for peer in peers})
    if not allowed:
        raise KitError(2, "at least one --to PEER is required")
    record = {"mode": "windows" if system.platform == "windows" else "ssh", "address": selected, "port": profile["port"], "peers": allowed, "scary": scary}
    prior = data.get("shares", {}).get(name)
    if prior and prior != record:
        raise KitError(8, "refused: share already has different settings; unshare it first")
    print(('Applying' if apply else 'PREVIEW') + ' for "{}": {}:{} -> {}:{}; requested peers: {}'.format(name, selected, profile["port"], LOOPBACK, profile["port"], ', '.join(allowed)))
    print('WARNING: CDP has no authentication; reachable programs control every signed-in tab.')
    if system.platform == "windows":
        print('Portproxy: netsh interface portproxy add v4tov4 listenaddress={} listenport={} connectaddress={} connectport={}'.format(selected, profile['port'], LOOPBACK, profile['port']))
        print('Firewall: ' + APP_NAME + '-' + name + ' allows TCP on that local address/port and its selected interface, only from ' + ', '.join(allowed) + '; companion -deny blocks all unlisted IPv4 peers, overriding broad allows.')
        print('Scheduled task: ' + APP_NAME + '-' + name + '-refresh runs as SYSTEM after boot, refreshing only this owned proxy; it never starts Chrome. Protected ProgramData stores its ownership record and refresh script.')
        print('Unshare removes only that proxy, both owned firewall rules, the refresh task and owned ledger/script. No service or default firewall changes.')
        print('--apply is explicit consent to these administrator changes. An elevated PowerShell is required; open it with Run as administrator and approve the UAC prompt, then rerun. Elevation is never silent.')
        argv = _windows(system, paths, name, record, "share", show_script)
        if apply:
            if system.cdp_version(profile["port"])["kind"] != "valid":
                raise KitError(5, "loopback CDP is not answering; open the profile first")
            code, out, err = system.run(argv, timeout=90)
            if code:
                raise KitError(8, "Windows share failed: " + (err or out).strip(), "inspect the error; rerun unshare --apply to clean up any owned partial installation")
            print(out.strip())
    else:
        print('Direct forwarding is unsupported on macOS/Linux: this kit does not manage their firewall policy.')
        print('SSH authenticates an existing account; --to records intended peers, NOT an SSH source-address ACL. Your SSH server must already be secured. No server, firewall or forwarder is installed.')
        print('On each listed agent machine, replace USER with the existing SSH account and keep this command running:\n' + ssh_command(selected, profile["port"]))
        print(SSH_NOTE)
        health = system.cdp_version(profile["port"])
        print('Browser-side loopback CDP: ' + ('verified' if health['kind'] == 'valid' else 'not answering'))
        print('Then verify on the agent machine:\ncurl --fail --show-error --max-time 5 http://' + LOOPBACK + ':' + str(profile['port']) + '/json/version')
        print('Tunnel authentication and reachability must be verified on the agent machine; --apply only records these instructions.')
        if apply and health["kind"] != "valid":
            raise KitError(5, "loopback CDP is not answering; open the profile first")
    if apply:
        data.setdefault("shares", {})[name] = record
        config.save(system, paths.config, data)
        print(("Applied sharing" if system.platform == "windows" else "Recorded SSH instructions; start and verify each tunnel") + " for " + name + ".")
    else:
        print('No network/system changes. Preview script saved; add --apply after review.' if system.platform == 'windows' else 'Nothing changed. Add --apply after reviewing the preview.')
    print('\nAGENT BRIEF\n' + brief(name, profile["port"], selected if system.platform == "windows" else LOOPBACK, apply and system.platform == "windows"))


def unshare(system, paths, data, name, apply=False, show_script=False):
    config.validate_name(name)
    record = data.get("shares", {}).get(name)
    if not record and not apply:
        print("No shares recorded; nothing to remove.")
        return
    if not record and system.platform != "windows":
        print("No shares recorded; nothing to remove.")
        return
    if not record:
        from .share_windows import status_script
        code, output, error = system.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", status_script(paths.config)], timeout=30)
        try:
            records = json.loads(output) if not code else None
            if not isinstance(records, dict):
                raise ValueError()
        except ValueError:
            raise KitError(8, "cannot inspect Windows sharing: " + (error or "invalid sharing status")) from None
        if name not in records:
            print("No shares recorded; nothing to remove.")
            return
    print(('Removing' if apply else 'PREVIEW: remove') + ' only owned sharing entries for "' + name + '"')
    if system.platform == "windows":
        print('Administrator consent required as for share; rerun in elevated PowerShell with --apply.')
        argv = _windows(system, paths, name, record, "unshare", show_script)
        if apply:
            code, out, err = system.run(argv, timeout=90)
            if code:
                raise KitError(8, "Windows unshare refused: " + (err or out).strip())
            print(out.strip())
    else:
        print('Remove the recorded SSH instructions only. Close the SSH command on each agent machine yourself; this tool cannot stop remote tunnels.')
    if apply and record:
        del data["shares"][name]
        config.save(system, paths.config, data)
    if apply:
        print("Removed owned sharing entries/instructions for " + name + ".")
    if not apply:
        print('No network/system changes. Preview script saved; add --apply after review.' if system.platform == 'windows' else 'Nothing changed. Add --apply after reviewing the preview.')


def status(system, paths, data):
    records = data.get("shares", {})
    if system.platform == "windows":
        # The protected machine ledger includes partial installations even if config saving failed.
        from .share_windows import status_script
        code, out, err = system.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", status_script(paths.config)], timeout=30)
        if code:
            raise KitError(8, "cannot inspect Windows sharing: " + (err or out).strip())
        try:
            records = json.loads(out)
        except ValueError:
            raise KitError(8, "invalid Windows sharing status") from None
    if not records:
        print('No shares recorded.')
    for name, record in sorted(records.items()):
        host = record["address"] if record["mode"] == "windows" else LOOPBACK
        probe = system.cdp_at(host, record["port"])
        print('{}: {}:{} -> peers {}; {}; {}'.format(name, record['address'], record['port'], ', '.join(record['peers']), record.get('state', 'SSH instructions only; tunnels are managed on peers'), 'CDP reachable from this machine' if probe['kind'] == 'valid' else 'CDP not reachable from this machine'))
    print('Local checks do not prove peer access restrictions. Run the brief health check from allowed and unlisted peers.')
