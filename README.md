# SAGE

Local-first, memory-augmented multi-model AI chat assistant.

## What It Does

SAGE is a chat assistant that intelligently routes between local (Ollama) and cloud (Groq) LLMs, with a long-term memory system that learns from conversations.

- **Smart routing** — a prompt analyzer classifies your message and picks the best available model
- **Cartridge system** — models are defined in a JSON registry, not code. Add or remove models without touching Python
- **Long-term memory** — every conversation turn is analyzed by a local model (gemma4:e2b). Important facts, preferences, and decisions are saved to SQLite and injected into future conversations
- **Offline-first** — works fully with local Ollama models. Cloud (Groq) is optional and used when available
- **Portable state** — memory DB and cartridge config live in `sage_state/`, copy it between machines

### Default Cartridges

| Cartridge | Provider | Model | Use Case |
|-----------|----------|-------|----------|
| cloud-fast | Groq | llama-3.3-70b-versatile | Fast general chat (online) |
| local-default | Ollama | gemma4:26b | General offline chat |
| local-heavy | Ollama | gemma4:31b | Deep reasoning, complex tasks |
| memory-core | Ollama | gemma4:e2b | Memory extraction & prompt analysis |

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com) running locally with models pulled:
  ```
  ollama pull gemma4:26b
  ollama pull gemma4:31b
  ollama pull gemma4:e2b
  ```
- (Optional) Groq API key from https://console.groq.com/keys

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env       # then add your GROQ_API_KEY if you have one
```

## Run

```bash
./run.sh
```

Or manually in two terminals:

```bash
python backend.py           # terminal 1 — backend on port 8000
streamlit run app.py        # terminal 2 — frontend on port 8501
```

Open http://localhost:8501 in your browser.

## Architecture

```
Streamlit UI (app.py)
    |
    | POST /chat
    v
Flask backend (backend.py)
    |
    |-- Prompt Analyzer (prompt_analyzer.py) --> classifies task type
    |-- Cartridge Registry (sage_state/cartridges.json) --> model config
    |-- Smart Router --> picks best cartridge
    |
    |-- Groq API (cloud, optional)
    |-- Ollama (local)
    |
    |-- Memory Engine (memory_engine.py)
            |
            v
        sage_state/brain_storage.db (SQLite)
```

## Adding a New Model

Edit `sage_state/cartridges.json` and add an entry:

```json
{
  "name": "my-model",
  "provider": "ollama",
  "model": "modelname:tag",
  "roles": ["general"],
  "online_required": false,
  "enabled": true,
  "priority": 55,
  "defaults": { "temperature": null, "num_ctx": 2048 }
}
```

Restart SAGE and the new cartridge appears in the UI.

## Portability

To transfer SAGE's brain between machines:

1. Copy the `sage_state/` directory
2. On the target machine, install Ollama and pull the same models
3. Run SAGE — it picks up where it left off
