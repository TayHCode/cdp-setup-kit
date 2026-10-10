APP_NAME = "cdp-setup-kit"
LOOPBACK = "127.0.0.1"
PORT_MIN = 1024
PORT_MAX = 65535
AUTO_PORTS = range(9222, 9322)
LINUX_MARKER = "X-Cdp-Setup-Kit-Managed=1"
MACOS_MARKER = "X-Cdp-Setup-Kit-Managed"
TASK_NAMESPACE = "http://schemas.microsoft.com/windows/2004/02/mit/task"
SECURITY_NOTICE = """SECURITY NOTICE
A Chrome window opened by this tool has a debugging port. Any program that
can reach that port can read and control every tab in that window, including
every site you are signed in to there. There is no password on the port.
Sign in only to the accounts you want your agents to use. The port listens on
this computer only. Do not forward it to a network you do not control."""

# Pinned MCP examples; verify and approve packages before installing them.
DEVTOOLS_MCP = "chrome-devtools-mcp@1.10.1"
PLAYWRIGHT_MCP = "@playwright/mcp@0.0.83"
