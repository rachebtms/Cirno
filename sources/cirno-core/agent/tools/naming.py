"""Namespaced model-facing tools over stable implementation identifiers.

Double underscores are accepted by function-calling APIs. PTC and the UI render
these as dots. Old identifiers remain usable for persisted calls and Python SDK
callers; only the namespaced surface is advertised to the model.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

with Path(__file__).with_name("names.json").open(encoding="utf-8") as stream:
    _catalog = json.load(stream)
NAMES = _catalog["names"]
ACTION_GROUPS = _catalog["action_groups"]
MEMORY_FIELDS = {
    "search": "query scope layer tags include_history mode limit offset since until purpose expand_links time_field time_zone",
    "read": "memory_id revision",
    "source": "memory_id revision start_line char_offset limit",
    "history": "memory_id",
    "tags": "query limit offset",
    "status": "",
    "link": "memory_id target_id relation source",
    "checkpoint": "content source expected_revision",
    "save": "content source scope kind layer title tags based_on observed_at",
    "update": "memory_id expected_revision content source scope kind layer title tags based_on observed_at",
    "confirm": "memory_id input_revision outcome target_ids reason",
}
NODE_FIELDS = {
    "list": "",
    "execute": "node_id command",
    "start": "node_id command",
    "status": "job_id",
    "stop": "job_id",
    "upload": "node_id local_path remote_path",
    "download": "node_id local_path remote_path",
}

MEMORY_DESCRIPTIONS = {
    "search": "Recall source-grounded memory. BM25 by default; semantic/hybrid uses the optional CPU worker. Knowledge is the default; use purpose=evidence to verify raw messages or exact values.",
    "read": "Read a memory and its provenance by ID, optionally at a historical revision.",
    "source": "Read original evidence behind a memory; continue with the returned line/character cursor.",
    "history": "Read the saved revision history of a memory.",
    "tags": "Discover available tags and counts; query is a tag prefix.",
    "status": "Read memory index and Dream processing status.",
    "link": "Link two memories with source-grounded supporting, conflicting or correcting evidence.",
    "checkpoint": "Save task progress: objective, completed work, blockers, next steps and exact artifact references.",
    "save": "Save an atomic observation, hypothesis, fact or lesson with a real source. Use based_on when deriving knowledge from existing evidence; never invent a source.",
    "update": "Update an event or knowledge record using the revision previously read. Profiles and task checkpoints have dedicated writers.",
    "confirm": "Confirm one Dream input with its revision, disposition and verified target IDs; restricted to the current evidence batch.",
}


def wire_name(name: str) -> str:
    return name.replace(".", "__")


def implementation_name(name: str) -> str:
    """Classify a namespaced or historical tool call for shared execution hooks."""
    if not isinstance(name, str):
        return ""
    dotted = name.replace("__", ".")
    for original, public in NAMES.items():
        if dotted == public:
            return original
    for original, group in ACTION_GROUPS.items():
        if dotted.startswith(group + "."):
            return original
    return name


def definitions(tool):
    """Yield (definition, bound action) without duplicating tool implementations."""
    schema = deepcopy(tool.to_schema())
    original = tool.name
    function = schema.get("function", schema)
    if original not in ACTION_GROUPS or not function.get("parameters", {}).get(
        "properties", {}
    ).get("action", {}).get("enum"):
        function["name"] = wire_name(NAMES.get(original, original))
        yield schema, None
        return
    properties = function["parameters"].get("properties", {})
    for action in properties["action"]["enum"]:
        if original == "memory" and (
            action == "confirm"
            and not getattr(tool, "maintenance", False)
            or action == "checkpoint"
            and getattr(tool, "maintenance", False)
        ):
            continue
        item = deepcopy(schema)
        fn = item.get("function", item)
        dotted = ACTION_GROUPS[original] + "." + action
        fn["name"] = wire_name(dotted)
        fn["description"] = (
            MEMORY_DESCRIPTIONS[action] if original == "memory" else f"{dotted}: {tool.description}"
        )
        params = fn["parameters"]
        fields = (
            MEMORY_FIELDS.get(action)
            if original == "memory"
            else NODE_FIELDS.get(action)
            if original == "node"
            else None
        )
        selected = set(fields.split()) if fields is not None else set(properties) - {"action"}
        params["properties"] = {key: value for key, value in properties.items() if key in selected}
        required = {
            "memory": {
                "read": ["memory_id"],
                "source": ["memory_id"],
                "history": ["memory_id"],
                "link": ["memory_id", "target_id", "source"],
                "save": ["content", "source"],
                "checkpoint": ["content", "source"],
                "update": ["memory_id", "expected_revision", "content", "source"],
                "confirm": ["memory_id", "input_revision", "outcome", "reason"],
            },
            "node": {
                "execute": ["node_id", "command"],
                "start": ["node_id", "command"],
                "status": ["job_id"],
                "stop": ["job_id"],
                "upload": ["node_id", "local_path", "remote_path"],
                "download": ["node_id", "local_path", "remote_path"],
            },
        }
        params["required"] = required.get(original, {}).get(
            action, [key for key in params.get("required", []) if key in selected]
        )
        params["additionalProperties"] = False
        yield item, action
