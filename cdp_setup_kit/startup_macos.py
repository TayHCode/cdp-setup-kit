from typing import List
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from .constants import APP_NAME, MACOS_MARKER
from .paths import Locations, path_module
from .system import System


def label(name: str) -> str:
    return APP_NAME + "-" + name


def entry_path(system: System, paths: Locations, name: str) -> str:
    return path_module(system).join(paths.startup, label(name) + ".plist")


def plist_text(name: str, argv: List[str]) -> str:
    arguments = "\n".join("    <string>" + escape(arg) + "</string>" for arg in argv)
    return '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{label}</string>
  <key>ProgramArguments</key>
  <array>
{arguments}
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <false/>
  <key>LimitLoadToSessionType</key>
  <string>Aqua</string>
  <key>{marker}</key>
  <string>1</string>
  <key>X-Cdp-Setup-Kit-Profile</key>
  <string>{name}</string>
</dict>
</plist>
'''.format(label=escape(label(name)), arguments=arguments, marker=MACOS_MARKER, name=escape(name))


def status(system: System, path: str, expected: str, name: str) -> str:
    # A link at the entry path is unfamiliar, even when its destination has our marker.
    if system.is_link(path):
        return "foreign"
    if not system.exists(path):
        return "disabled"
    try:
        actual = system.read_text(path)
        root = ET.fromstring(actual)
        if root.tag != "plist" or root.get("version") != "1.0" or len(root) != 1 or root[0].tag != "dict":
            return "foreign"
        fields, children = {}, list(root[0])
        if len(children) % 2:
            return "foreign"
        for index in range(0, len(children), 2):
            key, value = children[index:index + 2]
            if key.tag != "key" or key.text in fields:
                return "foreign"
            fields[key.text] = (value.tag, value.text)
        if (fields.get(MACOS_MARKER) != ("string", "1") or
                fields.get("Label") != ("string", label(name)) or
                fields.get("X-Cdp-Setup-Kit-Profile") != ("string", name)):
            return "foreign"
        return "enabled" if actual == expected else "stale"
    except (OSError, UnicodeError, ET.ParseError, ValueError):
        return "foreign"
