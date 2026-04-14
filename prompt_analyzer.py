import json
from typing import Any

import requests


VALID_TASK_TYPES = {"chat", "reasoning", "coding", "memory", "tooling", "other"}
VALID_LATENCY = {"fast", "normal", "slow_ok"}


def _build_system_prompt(cartridge_info: str) -> str:
    return f"""You are Sage's prompt analyzer.

Your job is to classify the user's message so the router can pick the best model cartridge.

Available cartridges and their roles:
{cartridge_info}

Output JSON only. No markdown. No explanation.

Return this schema exactly:
{{
  "task_type": "chat | reasoning | coding | memory | tooling | other",
  "complexity": 0,
  "needs_cloud": false,
  "needs_tools": false,
  "latency_preference": "fast | normal | slow_ok",
  "preferred_roles": ["general"],
  "avoid_roles": [],
  "recommended_cartridge": null,
  "confidence": 0.0,
  "notes": ""
}}

Rules:
- task_type must be one of: chat, reasoning, coding, memory, tooling, other
- complexity must be 0 (simple), 1 (moderate), or 2 (complex)
- needs_cloud: true only if the task clearly benefits from a large cloud model
- latency_preference: "fast" for simple chat, "normal" for most tasks, "slow_ok" for deep reasoning
- preferred_roles: list of cartridge roles that fit the task (e.g. ["general"], ["reasoning", "coding"])
- recommended_cartridge: name of the best cartridge if obvious, otherwise null
- confidence: 0.0 to 1.0
"""


def _build_user_prompt(messages: list[dict]) -> str:
    last_user = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user = m.get("content", "")
            break

    context_messages = messages[-4:] if len(messages) > 4 else messages
    context_summary = []
    for m in context_messages:
        role = m.get("role", "unknown")
        content = m.get("content", "")
        if content:
            preview = content[:200] + "..." if len(content) > 200 else content
            context_summary.append({"role": role, "content": preview})

    return json.dumps({
        "current_user_message": last_user,
        "recent_context": context_summary,
    }, ensure_ascii=False)


def _format_cartridge_info(enabled_cartridges: dict[str, dict]) -> str:
    lines = []
    for name, cart in enabled_cartridges.items():
        roles = cart.get("roles", [])
        provider = cart.get("provider", "unknown")
        model = cart.get("model", "unknown")
        lines.append(f"- {name}: provider={provider}, model={model}, roles={roles}")
    return "\n".join(lines)


def validate_analysis(raw: dict[str, Any]) -> dict[str, Any]:
    cleaned = {
        "task_type": str(raw.get("task_type", "chat")).strip().lower(),
        "complexity": int(raw.get("complexity", 0) or 0),
        "needs_cloud": bool(raw.get("needs_cloud", False)),
        "needs_tools": bool(raw.get("needs_tools", False)),
        "latency_preference": str(raw.get("latency_preference", "normal")).strip().lower(),
        "preferred_roles": raw.get("preferred_roles", ["general"]),
        "avoid_roles": raw.get("avoid_roles", []),
        "recommended_cartridge": raw.get("recommended_cartridge"),
        "confidence": float(raw.get("confidence", 0.0) or 0.0),
        "notes": str(raw.get("notes", "")).strip(),
    }

    if cleaned["task_type"] not in VALID_TASK_TYPES:
        cleaned["task_type"] = "chat"

    cleaned["complexity"] = max(0, min(cleaned["complexity"], 2))
    cleaned["confidence"] = max(0.0, min(cleaned["confidence"], 1.0))

    if cleaned["latency_preference"] not in VALID_LATENCY:
        cleaned["latency_preference"] = "normal"

    if not isinstance(cleaned["preferred_roles"], list):
        cleaned["preferred_roles"] = ["general"]
    cleaned["preferred_roles"] = [str(r).strip() for r in cleaned["preferred_roles"] if str(r).strip()]
    if not cleaned["preferred_roles"]:
        cleaned["preferred_roles"] = ["general"]

    if not isinstance(cleaned["avoid_roles"], list):
        cleaned["avoid_roles"] = []
    cleaned["avoid_roles"] = [str(r).strip() for r in cleaned["avoid_roles"] if str(r).strip()]

    if cleaned["recommended_cartridge"] is not None:
        cleaned["recommended_cartridge"] = str(cleaned["recommended_cartridge"]).strip() or None

    return cleaned


def analyze_prompt(
    *,
    messages: list[dict],
    ollama_base_url: str,
    analyzer_model: str,
    enabled_cartridges: dict[str, dict],
) -> dict[str, Any]:
    cartridge_info = _format_cartridge_info(enabled_cartridges)
    system_prompt = _build_system_prompt(cartridge_info)
    user_prompt = _build_user_prompt(messages)

    response = requests.post(
        f"{ollama_base_url}/api/chat",
        json={
            "model": analyzer_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "format": "json",
            "options": {
                "num_ctx": 1024,
                "temperature": 0.1,
            },
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    content = data.get("message", {}).get("content", "").strip()

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        # Attempt to extract JSON object from mixed output
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end > start:
            parsed = json.loads(content[start:end + 1])
        else:
            raise RuntimeError(f"Analyzer did not return valid JSON: {content}")

    return validate_analysis(parsed)
