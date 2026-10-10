import re
from typing import List, Optional
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from .constants import APP_NAME, TASK_NAMESPACE
from .errors import KitError
from .system import System


def task_name(name: str) -> str:
    return APP_NAME + "-" + name


def query_argv(name: str) -> List[str]:
    return ["schtasks", "/Query", "/TN", task_name(name), "/XML"]


def create_argv(name: str, path: str, force: bool = False) -> List[str]:
    return ["schtasks", "/Create", "/TN", task_name(name), "/XML", path] + (["/F"] if force else [])


def delete_argv(name: str) -> List[str]:
    return ["schtasks", "/Delete", "/TN", task_name(name), "/F"]


def task_xml(system: System, name: str, argv: List[str]) -> str:
    try:
        user = system.windows_account()
    except OSError:
        raise KitError(6, "Windows security identity is unavailable") from None
    if not user:
        raise KitError(6, "Windows account name is unavailable")
    values = {"ns": TASK_NAMESPACE, "app": APP_NAME, "name": name, "user": user,
              "command": argv[0], "args": system.join_windows_args(argv[1:])}
    return '''<Task version="1.2" xmlns="{ns}">
  <RegistrationInfo>
    <Source>{app}</Source>
    <Description>Managed by {app}. Opens the {name} Chrome window with its debugging port at sign-in.</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{user}</UserId>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{user}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>false</AllowHardTerminate>
    <StartWhenAvailable>false</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{command}</Command>
      <Arguments>{args}</Arguments>
    </Exec>
  </Actions>
</Task>
'''.format(**{key: escape(value) for key, value in values.items()})


def inspect_xml(text: str, expected: Optional[List[str]], system: System) -> str:
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text.lstrip("\ufeff"))
    try:
        root = ET.fromstring(text)
        ns = {"t": TASK_NAMESPACE}
        if root.findtext("t:RegistrationInfo/t:Source", namespaces=ns) != APP_NAME:
            return "foreign"
        if expected is None:
            return "stale"
        command = root.findtext("t:Actions/t:Exec/t:Command", namespaces=ns)
        args = root.findtext("t:Actions/t:Exec/t:Arguments", namespaces=ns)
        return "enabled" if command == expected[0] and args == system.join_windows_args(expected[1:]) else "stale"
    except (ET.ParseError, ValueError):
        return "foreign"


def status(system: System, name: str, expected: Optional[List[str]]) -> str:
    try:
        code, out, _ = system.run(query_argv(name))
    except OSError:
        raise KitError(6, "Windows task query failed") from None
    return "disabled" if code else inspect_xml(out, expected, system)
