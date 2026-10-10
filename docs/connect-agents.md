# Connect existing agents

Give the agent the HTTP endpoint, such as `http://127.0.0.1:9333`.
Do not save a `ws://` address: its last part changes each time Chrome starts.
Clients look up the current address from `/json/version` when connecting.
After a restart or reboot, reconnect to the same HTTP endpoint.

Use the window's existing context: `browser.contexts()[0]` in Node.js or
`browser.contexts[0]` in Python. That context holds the sign-ins. A context
made with `newContext()` is separate and starts signed out. Do not use a
client call that launches a new browser.

## Playwright with Node.js

Install Playwright separately according to its documentation, then adapt
[the Node.js example](../examples/playwright-attach.mjs). Its attach call is:

```js
const browser = await chromium.connectOverCDP('http://127.0.0.1:9333');
const context = browser.contexts()[0];
```

The example reuses the first page or opens one in that context, visits
`https://example.com`, and prints its title. Its final `browser.close()`
disconnects the attached client and leaves the window open.

## Playwright with Python

Use [the Python example](../examples/playwright_attach.py):

```python
browser = playwright.chromium.connect_over_cdp("http://127.0.0.1:9333")
context = browser.contexts[0]
```

It uses the same existing-context pattern and disconnects at the end.
The launcher does not depend on either Playwright package.

## MCP servers

Use [Playwright MCP settings](../examples/mcp-playwright.json) or
[Chrome DevTools MCP settings](../examples/mcp-chrome-devtools.json) in your
client's `mcpServers` configuration. Their commands are:

```sh
npx @playwright/mcp@0.0.83 --cdp-endpoint http://127.0.0.1:9333
npx chrome-devtools-mcp@1.10.1 --browser-url=http://127.0.0.1:9333
```

Chrome DevTools MCP collects usage statistics unless disabled. Read its
README for the current opt-out setting. The setup kit sends no statistics.
Use the explicit endpoint instead of a client's auto-connect route, which
can use Chrome's session approval dialog.

## Other CDP clients

Fetch `webSocketDebuggerUrl` from `http://127.0.0.1:PORT/json/version` when
connecting. To see it now:

```sh
cdp-setup-kit connect NAME --ws
```

It is a current address, not a permanent setting. Ordinary `connect` makes
no HTTP request. `list` checks endpoints without listing tabs.

## Shared windows

One agent per window is simplest. Several clients share tabs and sign-ins
when attached to the same window. Use another profile when work must stay separate.

## Checked as of 2026-10

The third-party commands were written from those projects' documentation.
Playwright and Playwright MCP attachment were checked on disposable macOS
and Windows profiles, locally and through SSH tunnels, including after browser
reopen. Chrome DevTools MCP remains unverified. Confirm each client's current
`--help` and see the exact limits in [verification](verification.md).

Use `127.0.0.1`, not `localhost`, in agent settings: some runtimes resolve
`localhost` to an address on which Chrome is not listening.

To close only this dedicated kit browser, preview `cdp-setup-kit stop NAME`, then
run `cdp-setup-kit stop NAME --apply`. It verifies the recorded profile before
asking Chrome to close and confirms that its endpoint disappears.
