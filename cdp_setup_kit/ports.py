from typing import Any, Dict, Optional, Tuple

from .config import validate_port
from .constants import AUTO_PORTS
from .errors import KitError
from .system import System


def busy_description(probe: Dict[str, Any]) -> str:
    return probe["data"]["Browser"] if probe["kind"] == "valid" else "something that is not a Chrome debugging endpoint"


def choose_port(system: System, data: Dict[str, Any], port: Optional[int] = None, name: str = "") -> Tuple[int, str]:
    assigned = {p["port"]: n for n, p in data["profiles"].items() if n != name}
    if port is None:
        for candidate in AUTO_PORTS:
            if candidate not in assigned and system.cdp_version(candidate)["kind"] == "refused" and system.can_bind(candidate):
                return candidate, ""
        raise KitError(4, "no free port from 9222 to 9321", "choose another with --port")
    validate_port(port)
    if port in assigned:
        raise KitError(10, "port is recorded for profile " + assigned[port])
    probe = system.cdp_version(port)
    if probe["kind"] != "refused" or not system.can_bind(port):
        return port, "warning: port {} is busy with {}".format(port, busy_description(probe))
    return port, ""
