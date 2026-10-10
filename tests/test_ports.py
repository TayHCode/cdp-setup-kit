from tests import support

from cdp_setup_kit.errors import KitError
from cdp_setup_kit.ports import choose_port


class PortTests(support.KitTestCase):
    def test_automatic_skips(self):
        data = {"profiles": {"work": {"port": 9222}}}
        self.system.busy.add(9223)
        self.system.probes[9224] = {"kind": "valid", "data": support.cdp_body()}
        self.assertEqual(choose_port(self.system, data), (9225, ""))

    def test_exhausted(self):
        self.system.busy.update(range(9222, 9322))
        with self.assertRaises(KitError) as caught:
            choose_port(self.system, {"profiles": {}})
        self.assertEqual(caught.exception.exit_code, 4)

    def test_recorded_elsewhere(self):
        with self.assertRaises(KitError) as caught:
            choose_port(self.system, {"profiles": {"shop": {"port": 9222}}}, 9222)
        self.assertEqual(caught.exception.exit_code, 10)
        self.assertIn("shop", str(caught.exception))

    def test_busy_warning(self):
        for probe in [{"kind": "not_cdp"}, {"kind": "valid", "data": support.cdp_body()}]:
            self.system.probes[9222] = probe
            port, warning = choose_port(self.system, {"profiles": {}}, 9222)
            self.assertEqual(port, 9222)
            self.assertIn("busy", warning)
