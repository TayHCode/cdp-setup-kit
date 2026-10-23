from tests import support
import json

from cdp_setup_kit.connect import instructions


class ConnectTests(support.KitTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli(["add", "work", "--port", "9222"])
        self.system.calls.clear()

    def test_golden_and_port_substitution(self):
        text = (support.ROOT / "tests/golden/connect-default.txt").read_text()
        self.assertEqual(self.run_cli(["connect", "work"])[1], text)
        self.assertEqual(instructions("work", 9223) + "\n", text.replace("9222", "9223"))
        self.assertFalse(any(call[0] == "probe" for call in self.system.calls))

    def test_external_instructions_use_supplied_address_without_local_commands(self):
        from cdp_setup_kit.connect import external_instructions
        address = "http://browser.example:9333"
        output = external_instructions(address)
        self.assertEqual(output.count(address), 5)
        self.assertIn("connectOverCDP", output)
        self.assertIn("connect_over_cdp", output)
        self.assertIn("--cdp-endpoint", output)
        self.assertIn("--browser-url=", output)
        for local_command in ("cdp-setup-kit list", "startup", "open main"):
            self.assertNotIn(local_command, output)

    def test_clients(self):
        for client, match in [("playwright", "connectOverCDP"), ("playwright-python", "connect_over_cdp"), ("playwright-mcp", "--cdp-endpoint"), ("chrome-devtools-mcp", "--browser-url="), ("curl", "/json/version")]:
            code, out, _ = self.run_cli(["connect", "work", "--client", client])
            self.assertEqual(code, 0)
            self.assertIn(match, out)

    def test_json_and_ws(self):
        row = json.loads(self.run_cli(["connect", "work", "--json"])[1])
        self.assertEqual(set(row), {"name", "port", "http_endpoint", "ws_endpoint"})
        self.assertIsNone(row["ws_endpoint"])
        self.assertEqual(self.run_cli(["connect", "work", "--ws"])[0], 5)
        self.system.probes[9222] = {"kind": "valid", "data": support.cdp_body()}
        self.assertIn("stops working", self.run_cli(["connect", "work", "--ws"])[1])
        self.assertEqual(json.loads(self.run_cli(["connect", "work", "--ws", "--json"])[1])["ws_endpoint"], support.cdp_body()["webSocketDebuggerUrl"])
