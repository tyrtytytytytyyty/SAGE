import os
from typing import Optional

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from openai import OpenAI

from memory_engine import MemoryEngine

# ----------------------------
# ENV SETUP
# ----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")

load_dotenv(dotenv_path=ENV_PATH)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:26b").strip()

print("Env path:", ENV_PATH)
print("Env exists:", os.path.exists(ENV_PATH))
print("GROQ_API_KEY loaded:", bool(GROQ_API_KEY))
print("GROQ model:", GROQ_MODEL)
print("Ollama model:", OLLAMA_MODEL)

# ----------------------------
# CLIENTS / CONSTANTS
# ----------------------------
app = Flask(__name__)

OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

groq_client: Optional[OpenAI] = None
if GROQ_API_KEY:
    groq_client = OpenAI(
        api_key=GROQ_API_KEY,
        base_url=GROQ_BASE_URL,
    )

memory_engine = MemoryEngine(
    db_path="brain_storage.db",
    memory_model="gemma4:e2b",
)

# ----------------------------
# CARTRIDGES
# ----------------------------
CARTRIDGES = {
    "cloud-fast": {
        "provider": "groq",
        "model": GROQ_MODEL,
    },
    "local-default": {
        "provider": "ollama",
        "model": OLLAMA_MODEL,
    },
    "local-heavy": {
        "provider": "ollama",
        "model": "gemma4:31b",
    },
}

# ----------------------------
# HELPERS
# ----------------------------
def check_online(timeout: int = 3) -> bool:
    try:
        requests.get("https://api.groq.com", timeout=timeout)
        return True
    except Exception:
        return False


def normalize_messages(messages: list[dict]) -> list[dict]:
    clean = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if content:
            clean.append({"role": role, "content": content})
    return clean


def get_current_user_message(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return m.get("content", "")
    return ""


def get_previous_assistant_message(messages: list[dict]) -> str:
    """
    Returns the assistant message before the current user message.
    Assumes the last user message is the active prompt.
    """
    if not messages:
        return ""

    earlier_messages = messages[:-1]

    for m in reversed(earlier_messages):
        if m.get("role") == "assistant":
            return m.get("content", "")
    return ""


def inject_memory_into_messages(messages: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Pull relevant long-term memories and prepend them as a system message.
    """
    current_user_message = get_current_user_message(messages)
    if not current_user_message:
        return messages, []

    memory_snippets = memory_engine.build_prompt_memory_snippets(
        query_text=current_user_message,
        max_complexity=2,
        limit=6,
    )

    if not memory_snippets:
        return messages, []

    memory_block = "Relevant long-term memory for this conversation:\n"
    for snippet in memory_snippets:
        memory_block += f"- {snippet}\n"

    memory_block += (
        "\nUse these memories only when relevant. "
        "Do not mention them unless naturally useful."
    )

    memory_message = {
        "role": "system",
        "content": memory_block
    }

    return [memory_message] + messages, memory_snippets


def call_ollama(messages: list[dict], model: str) -> tuple[str, str, str]:
    response = requests.post(
        OLLAMA_CHAT_URL,
        json={
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_ctx": 1024
            },
        },
        timeout=300,
    )
    response.raise_for_status()
    data = response.json()

    content = data.get("message", {}).get("content", "")
    if not content:
        raise RuntimeError("Ollama returned no content.")

    return content, "ollama", model


def call_groq(messages: list[dict], model: str) -> tuple[str, str, str]:
    if groq_client is None:
        raise RuntimeError("GROQ_API_KEY is missing.")

    response = groq_client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.7,
    )

    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("Groq returned no content.")

    return content, "groq", model


def run_cartridge(cartridge_name: str, messages: list[dict]) -> tuple[str, str, str]:
    if cartridge_name not in CARTRIDGES:
        raise RuntimeError(f"Unknown cartridge: {cartridge_name}")

    cart = CARTRIDGES[cartridge_name]
    provider = cart["provider"]
    model = cart["model"]

    if provider == "groq":
        return call_groq(messages, model)
    if provider == "ollama":
        return call_ollama(messages, model)

    raise RuntimeError(f"Unsupported provider: {provider}")


def auto_route(messages: list[dict]) -> str:
    last_user_message = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user_message = m.get("content", "").lower()
            break

    heavy_keywords = [
        "finalize",
        "final",
        "production",
        "architecture",
        "refactor",
        "optimize",
        "debug deeply",
        "large codebase",
    ]

    if any(k in last_user_message for k in heavy_keywords):
        return "local-heavy"

    if GROQ_API_KEY and check_online():
        return "cloud-fast"

    return "local-default"


def save_turn_to_memory(
    messages: list[dict],
    assistant_content: str,
    provider: str,
    model: str,
    cartridge: str,
):
    try:
        current_user_message = get_current_user_message(messages)
        previous_assistant_message = get_previous_assistant_message(messages)

        if not current_user_message or not assistant_content:
            return None

        result = memory_engine.process_turn(
            user_message=current_user_message,
            assistant_message=assistant_content,
            previous_assistant_message=previous_assistant_message,
            provider=provider,
            model=model,
            cartridge=cartridge,
            auto_maintain=True,
        )

        print("Memory process result:", result)
        return result

    except Exception as e:
        print("Memory processing failed:", repr(e))
        return None

# ----------------------------
# ROUTES
# ----------------------------
@app.get("/health")
def health():
    return jsonify(
        {
            "ok": True,
            "env_exists": os.path.exists(ENV_PATH),
            "groq_configured": bool(GROQ_API_KEY),
            "groq_model": GROQ_MODEL,
            "ollama_model": OLLAMA_MODEL,
            "memory_model": memory_engine.memory_model,
            "cartridges": CARTRIDGES,
        }
    )


@app.post("/chat")
def chat():
    data = request.get_json(force=True)

    messages = normalize_messages(data.get("messages", []))
    mode = data.get("mode", "auto")
    cartridge = data.get("cartridge")

    if not messages:
        return jsonify({"error": "No messages provided."}), 400

    try:
        augmented_messages, used_memories = inject_memory_into_messages(messages)

        # explicit cartridge wins
        if cartridge:
            content, provider, model = run_cartridge(cartridge, augmented_messages)
            save_turn_to_memory(messages, content, provider, model, cartridge)
            return jsonify(
                {
                    "provider": provider,
                    "model": model,
                    "cartridge": cartridge,
                    "content": content,
                    "used_memories": used_memories,
                }
            )

        # explicit provider modes
        if mode == "groq":
            content, provider, model = run_cartridge("cloud-fast", augmented_messages)
            save_turn_to_memory(messages, content, provider, model, "cloud-fast")
            return jsonify(
                {
                    "provider": provider,
                    "model": model,
                    "cartridge": "cloud-fast",
                    "content": content,
                    "used_memories": used_memories,
                }
            )

        if mode == "ollama":
            content, provider, model = run_cartridge("local-default", augmented_messages)
            save_turn_to_memory(messages, content, provider, model, "local-default")
            return jsonify(
                {
                    "provider": provider,
                    "model": model,
                    "cartridge": "local-default",
                    "content": content,
                    "used_memories": used_memories,
                }
            )

        # auto mode
        chosen = auto_route(messages)
        try:
            content, provider, model = run_cartridge(chosen, augmented_messages)
            save_turn_to_memory(messages, content, provider, model, chosen)
            return jsonify(
                {
                    "provider": provider,
                    "model": model,
                    "cartridge": chosen,
                    "content": content,
                    "used_memories": used_memories,
                }
            )
        except Exception as e:
            print(f"Primary cartridge failed ({chosen}):", repr(e))

            if chosen != "local-default":
                content, provider, model = run_cartridge("local-default", augmented_messages)
                save_turn_to_memory(messages, content, provider, model, "local-default")
                return jsonify(
                    {
                        "provider": provider,
                        "model": model,
                        "cartridge": "local-default",
                        "content": content,
                        "fallback": True,
                        "used_memories": used_memories,
                    }
                )

            raise

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/memory/view")
def memory_view():
    include_archived = request.args.get("include_archived", "false").lower() == "true"
    limit = int(request.args.get("limit", 200))
    memories = memory_engine.view_memories(include_archived=include_archived, limit=limit)
    return jsonify({"memories": memories})


@app.get("/memory/<int:memory_id>")
def memory_get(memory_id: int):
    memory = memory_engine.get_memory_by_id(memory_id)
    if not memory:
        return jsonify({"error": "Memory not found."}), 404
    return jsonify(memory)


@app.post("/memory/<int:memory_id>/edit")
def memory_edit(memory_id: int):
    data = request.get_json(force=True)
    edited_text = data.get("edited_text", "").strip()

    if not edited_text:
        return jsonify({"error": "edited_text is required."}), 400

    try:
        updated = memory_engine.edit_memory_from_text(memory_id, edited_text)
        return jsonify({"ok": True, "updated": updated})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/memory/<int:memory_id>/archive")
def memory_archive(memory_id: int):
    try:
        with memory_engine._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE memory_units
                SET archived = 1
                WHERE id = ?
            """, (memory_id,))
            conn.commit()
        return jsonify({"ok": True, "memory_id": memory_id, "archived": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/memory/<int:memory_id>/unarchive")
def memory_unarchive(memory_id: int):
    try:
        memory_engine.unarchive_memory(memory_id)
        return jsonify({"ok": True, "memory_id": memory_id, "archived": False})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.delete("/memory/<int:memory_id>")
def memory_delete(memory_id: int):
    try:
        memory_engine.delete_memory(memory_id)
        return jsonify({"ok": True, "memory_id": memory_id, "deleted": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)