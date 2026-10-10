# Changelog

## Unreleased

- Preview `stop NAME` and verify the owned loopback listener before DevTools graceful close; confirm endpoint shutdown without forcing process exit.
- Describe Windows SSH shells accurately and run owned interactive tasks with honest already-running feedback.
- Put the init result first, add explicit quiet mode, include SSH tunnel guidance in briefs, and simplify empty unshare previews.
- Refuse visible launches without a desktop; give the Windows interactive-task and Linux headless routes.
- Record new init profiles only after a successful requested open; print no-open settings explicitly.
- Support Linux `open --headless`; document Chrome installation and exact default port allocation.
- Preview startup without installed Chrome, clarify removal output, and improve diagnostics.
- Handle temporary profile files disappearing during cleanup on older Python versions.

## 0.2.0

- Explicit Windows sharing: previews, administrator consent, owned private-address portproxy, scoped allow/block firewall rules and protected boot refresh task. Idempotent apply, refusal of foreign/drifted resources, recovery of partial installations and exact unshare.
- macOS/Linux SSH tunnel instructions and loopback health checks; no direct forwarder or firewall management.
- Agent briefs with signed-in browser rules, HTTP MCP configs, health check, and optional file output. Share status and shared-profile mutation guards.
- Disposable live Windows peer isolation/removal and macOS/Linux tunnel checks; reboot and visible desktop checks remain owner work.

## 0.1.0 (unreleased)

- Guided `init`, repeatable `add`, and visible `open` with fixed endpoints.
- `list`, `doctor`, and `connect` with agent attach examples.
- Previewed `startup status`, `startup enable`, and `startup disable`.
- Explicit `set-port` and `remove`, retaining sign-in data by default.
- macOS direct Chrome launches, dedicated storage and previewed LaunchAgent sign-in entries, with fake and golden tests.
- Windows, Linux and macOS setup documentation; partial real-machine checks are recorded in docs/verification.md.
