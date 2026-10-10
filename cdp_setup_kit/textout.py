from typing import Any, Dict, List


HIDDEN = set(range(0x200B, 0x2010)) | set(range(0x202A, 0x202F)) | set(range(0x2066, 0x206A)) | {0xFEFF}


def clean_text(value: str, limit: int = 200) -> str:
    """Make text from another program safe to print: no control or format characters, bounded length."""
    cleaned = "".join("?" if not char.isprintable() or ord(char) in HIDDEN else char for char in value)
    return cleaned if len(cleaned) <= limit else cleaned[:limit] + "..."


def list_table(rows: List[Dict[str, Any]]) -> str:
    fields = ["name", "port", "http_endpoint", "status", "startup", "browser"]
    cells = [["NAME", "PORT", "ENDPOINT", "STATUS", "STARTUP", "BROWSER"]]
    cells += [["running (endpoint answers)" if field == "status" and row.get(field) == "running" else str(row.get(field) if row.get(field) is not None else "-") for field in fields] for row in rows]
    widths = [max(len(row[index]) for row in cells) for index in range(len(fields))]
    return "\n".join("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)).rstrip() for row in cells)
