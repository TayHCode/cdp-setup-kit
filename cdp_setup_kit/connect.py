import json
from typing import Any, Dict

from .constants import DEVTOOLS_MCP, PLAYWRIGHT_MCP
from .endpoint import http_endpoint
from .errors import KitError
from .profiles import get_profile
from .system import System
from .textout import clean_text


def client_instructions(address: str, client: str = "all"):
    sections = {
        "playwright": "Playwright (Node.js):\n  const browser = await chromium.connectOverCDP('" + address + "');\n  const context = browser.contexts()[0];",
        "playwright-python": 'Playwright (Python):\n  browser = playwright.chromium.connect_over_cdp("' + address + '")\n  context = browser.contexts[0]',
        "playwright-mcp": "Playwright MCP server:\n  npx " + PLAYWRIGHT_MCP + " --cdp-endpoint " + address,
        "chrome-devtools-mcp": "Chrome DevTools MCP server:\n  npx " + DEVTOOLS_MCP + " --browser-url=" + address,
        "curl": "Read the endpoint metadata (this does not list your tabs):\n  curl " + address + "/json/version",
    }
    return [sections[key] for key in ("playwright", "playwright-python", "playwright-mcp", "chrome-devtools-mcp")] if client == "all" else [sections[client]]


def external_instructions(address: str) -> str:
    return "\n\n".join(["Attach to the existing browser context. A new context starts signed out."]
                          + client_instructions(address)
                          + ["Check the endpoint: curl " + address + "/json/version"])


def instructions(name: str, port: int, client: str = "all") -> str:
    address = http_endpoint(port)
    intro = '''Profile "{}" listens at:  {}

Give your agent that HTTP address, not a ws:// address. The ws:// address
changes every time the browser starts. The HTTP address does not. Clients
look up the current ws:// address from it each time they connect.

Attach to the window's existing context. A new context starts signed out.'''.format(name, address)
    return "\n\n".join([intro] + client_instructions(address, client) + ["Check that it is up (this does not list your tabs):\n  cdp-setup-kit list", "More: docs/connect-agents.md"])


def show(system: System, data: Dict[str, Any], name: str, client: str = "all", ws: bool = False, as_json: bool = False) -> None:
    profile = get_profile(data, name)
    address = None
    if ws:
        probe = system.cdp_version(profile["port"])
        if probe["kind"] != "valid":
            raise KitError(5, "the endpoint is not answering", "run open " + name + ", then try again")
        address = clean_text(probe["data"]["webSocketDebuggerUrl"], 500)
    if as_json:
        print(json.dumps({"name": name, "port": profile["port"], "http_endpoint": http_endpoint(profile["port"]), "ws_endpoint": address}))
    else:
        print(instructions(name, profile["port"], client))
        if ws:
            print("\n" + address + "\nThis address stops working when the browser restarts. Fetch it again each time.")
