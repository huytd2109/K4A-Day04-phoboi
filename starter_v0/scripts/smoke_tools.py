from __future__ import annotations

import inspect
import os
import tempfile
from importlib import import_module
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(ROOT))

from tools import TOOL_FUNCTIONS, load_tool_declarations


failures: list[str] = []
checks_run = 0


def check(label: str, condition: bool, detail: Any = None) -> None:
    global checks_run
    checks_run += 1
    status = "PASS" if condition else "FAIL"
    suffix = "" if detail is None else f" - {detail}"
    print(f"{status} {label}{suffix}")
    if not condition:
        failures.append(label)


def main() -> None:
    declarations = load_tool_declarations(ROOT / "artifacts" / "tools.yaml")
    names = [item["name"] for item in declarations]
    declaration_names = set(names)
    registry_names = set(TOOL_FUNCTIONS)
    doc_names = {path.parent.name for path in (ROOT / "tools").glob("*/TOOL.md")}

    check("declaration names are unique", len(names) == len(declaration_names), names)
    check("tools.yaml matches runtime registry", declaration_names == registry_names)
    check("tools.yaml matches TOOL.md folders", declaration_names == doc_names)

    schema_signature_ok = True
    for item in declarations:
        name = item["name"]
        schema = item["parameters"]
        properties = set(schema.get("properties", {}))
        required = set(schema.get("required", []))
        signature = inspect.signature(TOOL_FUNCTIONS[name])
        function_args = set(signature.parameters)
        if not required <= properties or properties != function_args:
            schema_signature_ok = False
            print(
                f"  mismatch {name}: properties={sorted(properties)}, "
                f"required={sorted(required)}, function={sorted(function_args)}"
            )
    check("schema arguments match implementation signatures", schema_signature_ok)

    by_name = {item["name"]: item for item in declarations}
    clarify_required = set(by_name["clarify"]["parameters"].get("required", []))
    ticket_schema = by_name["create_ticket"]["parameters"]
    ticket_required = set(ticket_schema.get("required", []))
    confirmed_values = ticket_schema["properties"]["confirmed"].get("enum", [])
    check(
        "clarify requires question and response_type",
        {"question", "response_type"} <= clarify_required,
        sorted(clarify_required),
    )
    check(
        "create_ticket requires executable confirmation",
        {"summary", "priority", "confirmed"} <= ticket_required and confirmed_values == [True],
        {"required": sorted(ticket_required), "confirmed_enum": confirmed_values},
    )

    clarify = TOOL_FUNCTIONS["clarify"](
        "Chọn môi trường", "choice", ["production", "staging"]
    )
    check(
        "clarify local smoke",
        clarify.get("awaiting_user") is True
        and clarify.get("response_type") == "choice"
        and clarify.get("options") == ["production", "staging"],
    )

    kb = TOOL_FUNCTIONS["search_kb"]("Outlook profile", "email", 2)
    check(
        "search_kb local smoke",
        not kb.get("error") and bool(kb.get("results")) and bool(kb.get("trust_boundary")),
        f"results={len(kb.get('results') or [])}",
    )

    status = TOOL_FUNCTIONS["check_service_status"]("vpn", "production")
    check(
        "check_service_status local smoke",
        not status.get("error")
        and status.get("service") == "vpn"
        and status.get("environment") == "production"
        and "status" in status
        and "checked_at" in status,
    )

    device = TOOL_FUNCTIONS["inspect_device"]("LT-318", "vpn")
    check(
        "inspect_device local smoke",
        not device.get("error")
        and device.get("asset_id") == "LT-318"
        and set(device.get("diagnostics", {})) == {"vpn"},
    )

    user = TOOL_FUNCTIONS["lookup_user"]("EMP-1007")
    check(
        "lookup_user local smoke",
        not user.get("error") and user.get("employee", {}).get("employee_id") == "EMP-1007",
    )

    formatted = TOOL_FUNCTIONS["format_incident_report"](
        [{"label": "VPN", "detail": "degraded"}], "technical", "VPN incident"
    )
    check(
        "format_incident_report local smoke",
        formatted.get("finding_count") == 1
        and formatted.get("template") == "technical"
        and "# VPN incident" in formatted.get("markdown", ""),
    )

    policy = TOOL_FUNCTIONS["policy"](
        "dữ liệu nào được gửi ra external tool", "external_tools", 2
    )
    check(
        "policy local smoke",
        not policy.get("error")
        and bool(policy.get("results"))
        and bool(policy.get("trust_boundary")),
        f"results={len(policy.get('results') or [])}",
    )

    ticket_dir = ROOT / "tickets"
    before = set(ticket_dir.glob("*.json")) if ticket_dir.exists() else set()
    unconfirmed = TOOL_FUNCTIONS["create_ticket"]("VPN dry run", "low", "LT-204", False)
    string_confirmed = TOOL_FUNCTIONS["create_ticket"](
        "VPN dry run", "low", "LT-204", "true"
    )
    after = set(ticket_dir.glob("*.json")) if ticket_dir.exists() else set()
    check(
        "create_ticket defensive dry-run",
        unconfirmed.get("status") == "needs_confirmation"
        and string_confirmed.get("status") == "needs_confirmation"
        and before == after,
        f"existing_files={len(after)}; new_files={len(after - before)}",
    )

    ticket_module = import_module("tools.create_ticket.tool")
    original_ticket_dir = ticket_module.TICKET_DIR
    try:
        with tempfile.TemporaryDirectory(prefix="day04-ticket-smoke-") as temp_dir:
            ticket_module.TICKET_DIR = Path(temp_dir)
            created = TOOL_FUNCTIONS["create_ticket"](
                "VPN confirmed smoke", "low", "LT-204", True
            )
            created_path = Path(created.get("path", ""))
            check(
                "create_ticket confirmed path in temporary directory",
                created.get("status") == "created"
                and created_path.exists()
                and created_path.parent == Path(temp_dir),
            )
    finally:
        ticket_module.TICKET_DIR = original_ticket_dir

    external = TOOL_FUNCTIONS["search_device_info"]
    blocked = external("Lenovo", "LT-318", "drivers", 2)
    previous_key = os.environ.pop("TAVILY_API_KEY", None)
    try:
        no_key = external("Lenovo", "ThinkPad T14 Gen 4", "drivers", 2)
    finally:
        if previous_key is not None:
            os.environ["TAVILY_API_KEY"] = previous_key
    check(
        "search_device_info privacy and no-key preflight",
        blocked.get("error") == "restricted_internal_identifier"
        and no_key.get("error") == "missing_api_key",
    )

    if failures:
        raise SystemExit(f"\n{len(failures)} smoke check(s) failed: {', '.join(failures)}")
    print(f"\nALL PASS ({checks_run} interface/local checks summarized above)")


if __name__ == "__main__":
    main()
