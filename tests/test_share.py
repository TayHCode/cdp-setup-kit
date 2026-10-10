from tests import support
import hashlib
import ipaddress
import json

from cdp_setup_kit import config, share, share_windows
from cdp_setup_kit.constants import LOOPBACK
from cdp_setup_kit.errors import KitError
from cdp_setup_kit.paths import locations

# Example tailnet addresses, not machine identities.
HOST = str(ipaddress.IPv4Address(0x6440000a))
PEER = str(ipaddress.IPv4Address(0x64400014))
OTHER = str(ipaddress.IPv4Address(0x6440001e))
PUBLIC = str(ipaddress.IPv4Address(0xc0000201))


class ShareTests(support.KitTestCase):
    def setUp(self):
        super().setUp()
        self.system.cdp_at = lambda host, port: self.system.cdp_version(port)
        self.assertEqual(self.run_cli(['add', 'work', '--port', '9480'])[0], 0)
        self.system.probes[9480] = {'kind': 'valid', 'data': support.cdp_body()}
        self.args = ['share', 'work', '--to', PEER, '--address', HOST]

    def data(self):
        return config.load(self.system, locations(self.system).config)

    def windows(self, result=(0, 'verified', '')):
        self.system.platform = 'windows'
        path = locations(self.system).config
        data = {'schema': 1, 'chrome_path': None, 'profiles': {'work': {'port': 9480, 'profile_dir': 'C:\\kit\\profiles\\work', 'created_by_kit': True, 'created': '2026-10-09T00:00:00Z'}}}
        config.save(self.system, path, data)
        self.system.runs[('powershell.exe',)] = result
        self.system.calls.clear()

    def test_ssh_preview_no_changes_and_exact_tunnel(self):
        before = self.data()
        self.system.calls.clear()
        code, out, err = self.run_cli(self.args)
        self.assertEqual((code, err), (0, ''))
        self.assertIn(share.ssh_command(HOST, 9480), out)
        self.assertIn('loopback CDP: verified', out)
        self.assertIn('NOT an SSH source-address ACL', out)
        self.assertIn('will be available', out)
        self.assertEqual(self.data(), before)
        self.assertFalse(any(c[0] in {'write_text', 'spawn', 'run'} for c in self.system.calls))

    def test_ssh_record_status_and_idempotent_unshare(self):
        code, out, _ = self.run_cli(self.args + ['--apply'])
        self.assertEqual(code, 0)
        self.assertIn('Recorded SSH instructions', out)
        self.assertEqual(self.run_cli(self.args + ['--apply'])[0], 0)
        code, out, _ = self.run_cli(['share-status'])
        self.assertEqual(code, 0)
        self.assertIn(PEER, out)
        self.assertIn('SSH instructions only', out)
        self.assertIn('reachable from this machine', out)
        before = self.data()
        self.assertEqual(self.run_cli(['unshare', 'work'])[0], 0)
        self.assertEqual(self.data(), before)
        for _ in range(2):
            code, out, _ = self.run_cli(['unshare', 'work', '--apply'])
            self.assertEqual(code, 0)
            self.assertTrue('Removed owned' in out or 'No shares recorded; nothing to remove.' in out)
            self.assertNotIn('PREVIEW:', out)
        self.assertEqual(self.data()['shares'], {})

    def test_macos_ssh_route(self):
        self.system.platform = 'macos'
        self.assertEqual(self.run_cli(self.args + ['--apply'])[0], 0)
        self.assertEqual(self.data()['shares']['work']['mode'], 'ssh')

    def test_windows_preview_saves_script_without_system_mutations(self):
        self.windows()
        before = self.data()
        code, out, err = self.run_cli(self.args)
        self.assertEqual((code, err), (0, ''))
        script = share_windows.script('work', {'mode':'windows', 'address':HOST, 'port':9480, 'peers':[PEER], 'scary':False}, locations(self.system).config, 'share')
        self.assertNotIn(script, out)
        self.assertIn('PREVIEW: not live yet', out)
        self.assertIn('Script SHA256: ' + hashlib.sha256(script.encode()).hexdigest(), out)
        self.assertIn('Script lines: ' + str(len(script.splitlines())), out)
        self.assertIn('--show-script', out)
        writes = [c for c in self.system.calls if c[0] == 'write_text']
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0][2], script)
        self.assertIn('Full script saved: ' + writes[0][1], out)
        self.assertLess(len(out.split('AGENT BRIEF')[0].splitlines()), 18)
        self.assertIn('Run as administrator', out)
        self.assertIn('companion -deny', out)
        self.assertIn(script, self.run_cli(self.args + ['--show-script'])[1])
        self.assertFalse(any(c[0] in {'run', 'spawn'} for c in self.system.calls))
        self.assertEqual(before, self.data())

    def test_windows_apply_runs_exact_preview(self):
        self.windows()
        preview = self.run_cli(self.args)[1]
        self.system.calls.clear()
        code, out, err = self.run_cli(self.args + ['--apply'])
        self.assertEqual((code, err), (0, ''))
        runs = [c for c in self.system.calls if c[0] == 'run']
        self.assertEqual(len(runs), 1)
        digest = hashlib.sha256(runs[0][1][-1].encode()).hexdigest()
        self.assertIn('Script SHA256: ' + digest, preview)
        self.assertIn('Script SHA256: ' + digest, out)
        self.assertNotIn('PREVIEW:', out)
        self.assertIn('Applied sharing', out)
        self.assertEqual(self.data()['shares']['work']['mode'], 'windows')
        self.assertIn('A Chrome browser window (dedicated profile work) is available at http://' + HOST, out)

    def test_windows_admin_foreign_and_drift_errors_preserve_config(self):
        for error in ['Administrator consent required', 'Refused existing portproxy', 'Refused foreign firewall rule', 'Refused changed refresh script']:
            self.windows((1, '', error))
            before = self.data()
            code, _, err = self.run_cli(self.args + ['--apply'])
            self.assertEqual(code, 8)
            self.assertIn(error, err)
            self.assertEqual(before, self.data())

    def test_windows_unshare_preview_apply_and_failure(self):
        self.windows()
        self.run_cli(self.args + ['--apply'])
        before = self.data()
        self.system.calls.clear()
        self.assertEqual(self.run_cli(['unshare', 'work'])[0], 0)
        self.assertFalse(any(c[0] == 'run' for c in self.system.calls))
        self.assertEqual(before, self.data())
        self.system.runs[('powershell.exe',)] = (1, '', 'Refused changed portproxy')
        self.assertEqual(self.run_cli(['unshare', 'work', '--apply'])[0], 8)
        self.assertEqual(before, self.data())
        self.system.runs[('powershell.exe',)] = (0, 'removed', '')
        self.assertEqual(self.run_cli(['unshare', 'work', '--apply'])[0], 0)
        self.assertEqual(self.data()['shares'], {})

    def test_windows_unshare_without_local_record_recovers_machine_ledger(self):
        self.windows((0, json.dumps({"work": {"state": "partial"}}), ""))
        self.assertEqual(self.run_cli(['unshare', 'work', '--apply'])[0], 0)
        command = [c for c in self.system.calls if c[0] == 'run'][-1][1][-1]
        self.assertIn('state.json', command)
        self.assertIn('Refused entries without ownership record', command)
        self.assertIn("$owner = '", command)

    def test_nothing_shared_writes_no_script_and_uses_profile_name(self):
        self.windows((0, '{}', ''))
        self.system.calls.clear()
        for apply in ([], ['--apply']):
            code, out, err = self.run_cli(['unshare', 'work'] + apply)
            self.assertEqual((code, err), (0, ''))
            self.assertIn('No shares recorded; nothing to remove.', out)
            self.assertNotIn('Administrator consent', out)
        self.assertFalse(any(c[0] in {'write_text', 'make_dir'} for c in self.system.calls))
        self.run_cli(self.args + ['--apply'])
        out = self.run_cli(['unshare', 'work'])[1]
        self.assertIn('entries for "work"', out)

    def test_brief_has_tunnel_without_share_or_with_remote_address(self):
        for args in [['agent-brief', 'work'], ['agent-brief', 'work', '--address', HOST]]:
            code, out, err = self.run_cli(args)
            self.assertEqual((code, err), (0, ''))
            self.assertIn('ssh -N -L 9480:', out)
            self.assertIn('USER@', out)

    def test_windows_status_reports_ledger_and_partial_failure(self):
        self.windows((0, json.dumps({'work': {'mode':'windows', 'address':HOST, 'port':9480, 'peers':[PEER], 'state':'partial'}}), ''))
        code, out, _ = self.run_cli(['share-status'])
        self.assertEqual(code, 0)
        self.assertIn('partial', out)
        self.assertIn(PEER, out)
        self.system.runs[('powershell.exe',)] = (1, '', 'access denied')
        self.assertEqual(self.run_cli(['share-status'])[0], 8)
        self.system.runs[('powershell.exe',)] = (0, 'invalid', '')
        self.assertEqual(self.run_cli(['share-status'])[0], 8)

    def test_dead_browser_refuses_apply_on_all_platforms(self):
        for platform in ['linux', 'macos', 'windows']:
            if platform == 'windows':
                self.windows()
            else:
                self.system.platform = platform
            self.system.probes[9480] = {'kind': 'refused'}
            self.assertEqual(self.run_cli(self.args + ['--apply'])[0], 5)
            self.assertNotIn('work', self.data().get('shares', {}))
            self.assertFalse(any(c[0] == 'run' for c in self.system.calls))

    def test_different_share_refuses_without_mutating(self):
        self.run_cli(self.args + ['--apply'])
        before = self.data()
        for extra in [['--to', OTHER], ['--address', OTHER]]:
            self.assertEqual(self.run_cli(self.args + extra + ['--apply'])[0], 8)
            self.assertEqual(self.data(), before)

    def test_recorded_share_blocks_port_change_and_removal(self):
        self.run_cli(self.args + ['--apply'])
        for args in [['set-port','work','9481','--apply'], ['remove','work','--apply']]:
            self.assertEqual(self.run_cli(args)[0], 8)
        self.assertEqual(self.data()['profiles']['work']['port'], 9480)

    def test_tailscale_default(self):
        self.system.binaries['tailscale'] = '/test/tailscale'
        self.system.runs[('/test/tailscale', 'ip', '-4')] = (0, HOST + '\n', '')
        self.assertEqual(self.run_cli(['share','work','--to',PEER])[0], 0)
        for out in ['', 'invalid', HOST + '\n' + OTHER, PUBLIC]:
            self.system.runs[('/test/tailscale', 'ip', '-4')] = (0, out, '')
            self.assertEqual(self.run_cli(['share','work','--to',PEER])[0], 2)

    def test_missing_address_peer_or_profile(self):
        self.assertEqual(self.run_cli(['share','work','--to',PEER])[0], 2)
        self.assertEqual(self.run_cli(['share','work','--address',HOST])[0], 2)
        self.assertEqual(self.run_cli(['share','absent','--to',PEER,'--address',HOST])[0], 3)

    def test_private_only_and_scary_override_still_refuses_wildcard(self):
        bad = [str(ipaddress.IPv4Address(0)), LOOPBACK, '::', '::1', 'localhost', HOST + '/32', HOST + ';oops', str(ipaddress.IPv4Address(0xe0000001)), str(ipaddress.IPv4Address(0xa9fe0101))]
        for value in bad:
            for scary in [False, True]:
                with self.subTest(value=value, scary=scary), self.assertRaises(KitError):
                    share.address(value, scary)
        with self.assertRaises(KitError):
            share.address(PUBLIC)
        self.assertEqual(share.address(PUBLIC, True), PUBLIC)
        self.assertEqual(self.run_cli(['share','work','--to',PEER,'--address',PUBLIC])[0], 2)
        self.assertEqual(self.run_cli(['share','work','--to',PEER,'--address',PUBLIC,'--i-understand-this-exposes-signed-in-browsers'])[0], 0)
        self.assertEqual(self.run_cli(['share','work','--to',PUBLIC,'--address',HOST])[0], 2)

    def test_brief_config_warning_and_write(self):
        target = str(self.folder / 'brief.txt')
        code, out, err = self.run_cli(['agent-brief','work','--address',HOST,'--write',target])
        self.assertEqual((code, err), (0, ''))
        self.assertEqual(self.system.read_text(target), out)
        for text in ['Chrome browser window (dedicated profile work) is available', '--browser-url=http://' + HOST, '--cdp-endpoint', 'CDP has no authentication', 'controls every tab', 'do not close other windows/tabs', 'never copy or export profiles/cookies', 'changing provider data through it is a write', '/json/version']:
            self.assertIn(text, out)
        json.loads(out[out.index('{'):out.rindex('}') + 1])
        self.assertEqual(self.run_cli(['agent-brief','work','--write',target])[0], 8)
        self.assertEqual(self.run_cli(['agent-brief','work','--address',PUBLIC])[0], 2)

    def test_brief_uses_recorded_windows_address_and_ssh_loopback(self):
        self.run_cli(self.args + ['--apply'])
        self.assertIn('http://' + LOOPBACK, self.run_cli(['agent-brief','work'])[1])
        self.windows()
        self.run_cli(self.args + ['--apply'])
        self.assertIn('http://' + HOST, self.run_cli(['agent-brief','work'])[1])

    def test_invalid_share_records_fail_closed(self):
        for record in [{'mode':'other'}, {'mode':'ssh','port':9480,'address':HOST,'peers':[]}, {'mode':'ssh','port':9480,'address':HOST,'peers':['bad']}]:
            data = self.data()
            data['shares'] = {'work':record}
            with self.assertRaises(KitError):
                config.validate(data, self.system)

    def test_boot_and_deletion_guard_script_contract(self):
        self.windows()
        out = self.run_cli(self.args + ['--show-script'])[1]
        for text in ['-AtStartup', "'PT30S'", '-User SYSTEM', '-RunLevel Highest', 'SafeLedger $refreshPath', 'ReparsePoint', 'Refused foreign', 'Refused existing or changed portproxy', 'Refused changed refresh script', 'connectaddress=' + LOOPBACK, '-InterfaceAlias $wanted.interface', '-RemoteAddress $wanted.peers', '-RemoteAddress $wanted.denied', '-Action Block', 'Stop-ScheduledTask', 'No automatic elevation']:
            self.assertIn(text, out)
        self.assertIn('$r.root_created -eq $true', out)
        self.assertNotIn('-Recurse -Force', out)
        self.assertNotIn('Set-NetFirewallProfile', out)
        self.assertNotIn('Start-Service', out)

    def test_block_scope_excludes_all_allowed_peers(self):
        record = {'mode':'windows','address':HOST,'port':9480,'peers':[PEER,OTHER], 'scary':False}
        script = share_windows.script('work', record, 'C:\\kit\\config.json', 'share')
        line = next(line for line in script.splitlines() if line.startswith('$wanted = '))
        raw = line[len("$wanted = '"):line.rindex("' | ConvertFrom-Json")]
        data = json.loads(raw)
        networks = [ipaddress.ip_network(n) for n in data['denied']]
        self.assertEqual(sum(n.num_addresses for n in networks), 2**32-2)
        for peer in [PEER,OTHER]:
            self.assertFalse(any(ipaddress.ip_address(peer) in n for n in networks))
        self.assertTrue(any(ipaddress.ip_address(HOST) in n for n in networks))

    def test_quoted_paths_cannot_inject_powershell(self):
        owner = "C:\\kit's folder\\config.json"
        script = share_windows.script('work', None, owner, 'unshare')
        self.assertIn("$owner = 'C:\\kit''s folder\\config.json'", script)
        self.assertIn("$wanted = 'null'", script)

    def test_changed_preview_file_refuses_apply_without_execution(self):
        self.windows()
        self.run_cli(self.args)
        path = next(c[1] for c in self.system.calls if c[0] == 'write_text')
        self.system.write_text(path, 'changed by someone else')
        self.system.calls.clear()
        self.assertEqual(self.run_cli(self.args + ['--apply'])[0], 8)
        self.assertFalse(any(c[0] in {'run', 'write_text'} for c in self.system.calls))
        self.assertEqual(self.system.read_text(path), 'changed by someone else')

    def test_ssh_brief_includes_authentication_guidance_and_pins(self):
        self.run_cli(self.args + ['--apply'])
        out = self.run_cli(['agent-brief', 'work'])[1]
        self.assertIn(share.ssh_command(HOST, 9480), out)
        for value in ['StrictHostKeyChecking=accept-new', 'answer yes once', '-i KEY', 'Host alias', 'impersonation risk']:
            self.assertIn(value, out)
        self.assertNotIn('@latest', out)
        self.assertIn('chrome-devtools-mcp@1.10.1', out)
        self.system.probes[9480] = {'kind': 'refused'}
        self.assertIn('PREVIEW: not live yet', self.run_cli(['agent-brief', 'work'])[1])
