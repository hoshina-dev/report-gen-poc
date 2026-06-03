"""
Context flattening — converts a raw experiment data payload into a flat
str→str dict suitable for {{field}} interpolation.

Rules:
- Top-level scalars (str, int, float, bool) → included directly.
- Any dict value that has a "questions" list (form-like structure) → each
  question's ``id`` becomes a key with ``[label]`` as a placeholder value.
- Other nested dicts → flatten one level deep with ``parent_key`` notation.
- Lists → skipped unless handled by a special rule above.
"""

import re
from typing import Any

# Only valid Python identifiers are usable as {{field}} names
_VALID_KEY = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


def flatten_context(data: dict[str, Any]) -> dict[str, str]:
    """
    Flatten *data* into a ``{field_name: str_value}`` dict.

    This is intentionally lossy: the goal is to provide simple string values
    for ``{{field}}`` interpolation, not to round-trip the full JSON.
    """
    context: dict[str, str] = {}

    for key, value in data.items():
        if isinstance(value, (str, int, float, bool)):
            if _VALID_KEY.match(key):
                context[key] = str(value)

        elif isinstance(value, dict):
            if "questions" in value and isinstance(value["questions"], list):
                # Form-like: use question default as value, fall back to [Label].
                # Never overwrite a top-level scalar already in context.
                for q in value["questions"]:
                    q_id = q.get("id", "")
                    q_label = q.get("label", q_id)
                    if q_id and _VALID_KEY.match(q_id) and q_id not in context:
                        default = q.get("default")
                        if default is not None and isinstance(
                            default, (str, int, float, bool)
                        ):
                            context[q_id] = str(default)
                        else:
                            context[q_id] = f"[{q_label}]"
            elif key == "calculations":
                # Expose calculation results directly by key (no prefix).
                # Plain scalar values are used as-is; expressions → placeholder.
                for sub_key, sub_val in value.items():
                    if _VALID_KEY.match(sub_key) and sub_key not in context:
                        if isinstance(sub_val, (str, int, float, bool)):
                            context[sub_key] = str(sub_val)
                        else:
                            context[sub_key] = f"[{sub_key}]"
            else:
                # Other nested dicts: flatten one level with parent_key notation
                for sub_key, sub_val in value.items():
                    flat = f"{key}_{sub_key}"
                    if isinstance(
                        sub_val, (str, int, float, bool)
                    ) and _VALID_KEY.match(flat):
                        context[flat] = str(sub_val)

        # Lists (other than questions already handled above) → skip for now

    return context


# ---------------------------------------------------------------------------
# Variable grouping (for the editor UI dropdown)
# ---------------------------------------------------------------------------

#: Ordered list of (json_key, display_name) for form-like sources
_FORM_SOURCES = [
    ("userForm", "User Form"),
    ("workerForm", "Worker Form"),
]


def group_variables(data: dict[str, Any]) -> list[dict]:
    """
    Return variables from *data* grouped by source, for the editor dropdown.

    Each group::

        {"name": "User Form", "variables": [{"id": "full_name", "label": "Full name"}, ...]}

    Sources, in order:
    - userForm.questions   → "User Form"
    - workerForm.questions → "Worker Form"
    - calculations keys    → "Calculations"
    """
    groups: list[dict] = []

    # Top-level scalar fields (e.g. template, name, sample_id)
    top_level = [
        {"id": k, "label": k}
        for k, v in data.items()
        if isinstance(v, (str, int, float, bool)) and _VALID_KEY.match(k)
    ]
    if top_level:
        groups.append({"name": "Fields", "variables": top_level})

    # Form-like objects
    for json_key, display_name in _FORM_SOURCES:
        form = data.get(json_key)
        if not isinstance(form, dict):
            continue
        variables = [
            {"id": q["id"], "label": q.get("label", q["id"])}
            for q in form.get("questions", [])
            if q.get("id") and _VALID_KEY.match(q["id"])
        ]
        if variables:
            groups.append({"name": display_name, "variables": variables})

    # Calculations
    calcs = data.get("calculations")
    if isinstance(calcs, dict):
        variables = [{"id": k, "label": k} for k in calcs if _VALID_KEY.match(k)]
        if variables:
            groups.append({"name": "Calculations", "variables": variables})

    return groups
