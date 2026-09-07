#!/usr/bin/env python3
"""Offline topology and configuration checks."""

from __future__ import annotations

import json
import re
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / "workflows" / "revenueflow-ai-lead-qualification.json"
EXPECTED_NAME = "RevenueFlow | AI Lead Qualification and Outreach"
EXPECTED_TOTAL_NODES = 53
EXPECTED_FUNCTIONAL_NODES = 48
EXPECTED_NOTES = 5
EXPECTED_EDGES = 57

SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "Telegram bot token": re.compile(r"(?<![A-Za-z0-9])\d{6,12}:[A-Za-z0-9_-]{20,}(?![A-Za-z0-9])"),
    "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    "provider API key": re.compile(r"\b(?:sk|xai|gsk|hf|pat)-[A-Za-z0-9_-]{16,}\b", re.I),
    "literal bearer token": re.compile(r"\bBearer\s+(?!YOUR_)[A-Za-z0-9._~+/-]{16,}={0,2}\b", re.I),
    "literal basic credential": re.compile(r"\bBasic\s+(?!YOUR_)[A-Za-z0-9+/]{16,}={0,2}\b", re.I),
}

ALLOWED_HOSTS = {
    "api.hubapi.com",
    "cal.com",
    "example.com",
    "github.com",
    "openrouter.ai",
}

URL_RE = re.compile(r"https?://[A-Za-z0-9._-]+", re.I)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,})\b", re.I)
NODE_REFERENCE_PATTERNS = (
    re.compile(r"\$\(\s*(['\"])(.*?)\1\s*\)"),
    re.compile(r"\$node\s*\[\s*(['\"])(.*?)\1\s*\]"),
    re.compile(r"\$items\s*\(\s*(['\"])(.*?)\1"),
)


def walk(value: Any, path: tuple[Any, ...] = ()) -> Iterable[tuple[tuple[Any, ...], Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = path + (key,)
            yield child_path, child
            yield from walk(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = path + (index,)
            yield child_path, child
            yield from walk(child, child_path)


def count_edges(connections: dict[str, Any]) -> int:
    total = 0
    for channels in connections.values():
        for output_groups in channels.values():
            for output_group in output_groups:
                total += len(output_group)
    return total


def node_by_name(nodes: list[dict], name: str) -> dict | None:
    return next((node for node in nodes if node.get("name") == name), None)


def public_host(host: str) -> bool:
    return host in ALLOWED_HOSTS or host.endswith(".example")


def public_email_domain(domain: str) -> bool:
    return domain == "example.com" or domain.endswith(".example")


def validate() -> list[str]:
    errors: list[str] = []
    try:
        doc = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - report parse failures
        return [f"invalid workflow JSON: {exc}"]

    nodes = doc.get("nodes")
    connections = doc.get("connections")
    if not isinstance(nodes, list) or not isinstance(connections, dict):
        return ["workflow must contain nodes and connections"]

    notes = [node for node in nodes if node.get("type") == "n8n-nodes-base.stickyNote"]
    functional = [node for node in nodes if node.get("type") != "n8n-nodes-base.stickyNote"]
    if doc.get("name") != EXPECTED_NAME:
        errors.append("unexpected workflow name")
    if len(nodes) != EXPECTED_TOTAL_NODES:
        errors.append(f"expected {EXPECTED_TOTAL_NODES} total nodes, found {len(nodes)}")
    if len(functional) != EXPECTED_FUNCTIONAL_NODES:
        errors.append(f"expected {EXPECTED_FUNCTIONAL_NODES} functional nodes, found {len(functional)}")
    if len(notes) != EXPECTED_NOTES:
        errors.append(f"expected {EXPECTED_NOTES} sticky notes, found {len(notes)}")
    if count_edges(connections) != EXPECTED_EDGES:
        errors.append(f"expected {EXPECTED_EDGES} connection edges, found {count_edges(connections)}")
    if doc.get("active") is not False:
        errors.append("workflow must import inactive")
    if "pinData" in doc:
        errors.append("pinData must not be included")

    names = [str(node.get("name", "")) for node in nodes]
    node_ids = [str(node.get("id", "")) for node in nodes]
    name_set = set(names)
    functional_names = {str(node.get("name", "")) for node in functional}
    if "" in name_set or len(name_set) != len(names):
        errors.append("node names must be present and unique")
    if "" in set(node_ids) or len(set(node_ids)) != len(node_ids):
        errors.append("node IDs must be present and unique")
    for node_id in node_ids:
        try:
            uuid.UUID(node_id)
        except ValueError:
            errors.append(f"node ID is not a UUID: {node_id!r}")

    adjacency: dict[str, set[str]] = {name: set() for name in functional_names}
    roots = {
        str(node.get("name", ""))
        for node in functional
        if str(node.get("type", "")).lower().endswith("trigger")
        or node.get("type") == "n8n-nodes-base.webhook"
    }
    for source, channels in connections.items():
        if source not in name_set:
            errors.append(f"unknown connection source {source!r}")
        for output_groups in channels.values():
            for output_group in output_groups:
                for target in output_group:
                    target_name = target.get("node")
                    if target_name not in name_set:
                        errors.append(f"unknown connection target {target_name!r}")
                    elif source in adjacency and target_name in functional_names:
                        adjacency[source].add(target_name)

    reachable: set[str] = set()
    pending = list(roots)
    while pending:
        current = pending.pop()
        if current in reachable:
            continue
        reachable.add(current)
        pending.extend(adjacency.get(current, ()))
    unreachable = sorted(functional_names - reachable)
    if unreachable:
        errors.append(f"unreachable functional nodes: {', '.join(unreachable)}")

    for item_path, value in walk(doc):
        key = str(item_path[-1]) if item_path else ""
        location = ".".join(str(part) for part in item_path)
        if key in {"credentials", "webhookId", "instanceId"}:
            errors.append(f"forbidden field {location}")
        if key in {"chatId", "accountId", "workflowId", "folderId", "fileId"} and value not in (None, ""):
            text_value = json.dumps(value, ensure_ascii=False)
            if not any(marker in text_value for marker in ("YOUR_", "{{", "$json", "$vars", "$(")):
                errors.append(f"non-placeholder identifier at {location}")
        if not isinstance(value, str):
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(value):
                errors.append(f"possible {label} at {location}")
        for match in EMAIL_RE.finditer(value):
            if not public_email_domain(match.group(1).lower()):
                errors.append(f"non-example email at {location}")
        for match in URL_RE.finditer(value):
            host = (urlsplit(match.group(0)).hostname or "").lower()
            if host and not public_host(host):
                errors.append(f"non-allowlisted literal URL host {host!r} at {location}")
        for pattern in NODE_REFERENCE_PATTERNS:
            for match in pattern.finditer(value):
                referenced = match.group(2)
                if referenced not in name_set:
                    errors.append(f"expression references unknown node {referenced!r} at {location}")

    expected_types = {
        "n8n-nodes-base.code": 25,
        "n8n-nodes-base.if": 10,
        "n8n-nodes-base.httpRequest": 4,
        "n8n-nodes-base.merge": 3,
        "n8n-nodes-base.gmail": 3,
        "n8n-nodes-base.manualTrigger": 1,
        "n8n-nodes-base.webhook": 1,
        "n8n-nodes-base.telegram": 1,
        "n8n-nodes-base.stickyNote": 5,
    }
    if Counter(node.get("type") for node in nodes) != Counter(expected_types):
        errors.append("node-type inventory changed")

    webhook = node_by_name(nodes, "Lead Intake Webhook")
    if not webhook or webhook.get("parameters", {}).get("path") != "revenueflow-lead-intake":
        errors.append("semantic lead-intake webhook path is missing")

    for name in ("Fetch Company Website", "OpenRouter: Analyze Lead", "Telegram: Alert Sales"):
        node = node_by_name(nodes, name)
        if not node or node.get("onError") != "continueRegularOutput":
            errors.append(f"{name} must use its configured fallback path")

    approval = node_by_name(nodes, "Gmail: Request Approval")
    wait_values = (
        (approval or {}).get("parameters", {})
        .get("options", {})
        .get("limitWaitTime", {})
        .get("values", {})
    )
    if wait_values != {"resumeAmount": 72, "resumeUnit": "hours"}:
        errors.append("approval wait limit must be 72 hours")

    serialized = json.dumps(doc, ensure_ascii=False)
    if "/crm/v3/" in serialized:
        errors.append("unsupported HubSpot CRM v3 route remains")
    for route in (
        "/crm/objects/2026-03/contacts/search",
        "/crm/objects/2026-03/contacts",
    ):
        if route not in serialized:
            errors.append(f"current HubSpot route is missing: {route}")
    for variable in (
        "REVENUEFLOW_DEMO_MODE",
        "REVENUEFLOW_BOOKING_URL",
        "REVENUEFLOW_APPROVAL_EMAIL",
        "REVENUEFLOW_TELEGRAM_CHAT_ID",
    ):
        if variable not in serialized:
            errors.append(f"required runtime variable is missing: {variable}")

    return sorted(set(errors))


def main() -> int:
    errors = validate()
    if errors:
        print(f"FAILED: {len(errors)} issue(s)")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PASS: 1 workflow, 53 nodes (48 functional + 5 notes), 57 edges")
    print("PASS: topology, reachability, references, inactive state, fallbacks, identifiers, hosts, and secret patterns")
    return 0


if __name__ == "__main__":
    sys.exit(main())
