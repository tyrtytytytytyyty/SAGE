import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Optional

import requests


class MemoryEngine:
    """
    Sage memory system:
    - logs raw turns
    - uses a small local model (gemma4:e2b) to analyze memory-worthiness
    - stores structured memory in SQLite
    - supports decay/archive/retrieval/view/edit
    """

    MEMORY_TYPES = {
        "preference": 1,
        "project_goal": 2,
        "architecture_decision": 3,
        "constraint": 4,
        "workflow": 5,
        "identity": 6,
        "correction": 7,
        "fact": 8,
        "temporary_context": 9,
    }
    REVERSE_MEMORY_TYPES = {v: k for k, v in MEMORY_TYPES.items()}

    def __init__(
        self,
        db_path: str = "brain_storage.db",
        ollama_base_url: str = "http://localhost:11434",
        memory_model: str = "gemma4:e2b",
    ):
        self.db_path = db_path
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.memory_model = memory_model
        self._bootstrap_db()

    # ----------------------------
    # BASIC UTILITIES
    # ----------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _now(self) -> str:
        return datetime.utcnow().isoformat()

    def _json_dumps(self, obj: Any) -> str:
        return json.dumps(obj, ensure_ascii=False)

    def _json_loads_safe(self, text: str, default: Any = None) -> Any:
        try:
            return json.loads(text)
        except Exception:
            return default

    # ----------------------------
    # DB BOOTSTRAP
    # ----------------------------
    def _bootstrap_db(self):
        with self._connect() as conn:
            cur = conn.cursor()

            cur.execute("""
            CREATE TABLE IF NOT EXISTS raw_turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_message TEXT,
                assistant_message TEXT,
                previous_assistant_message TEXT,
                provider TEXT,
                model TEXT,
                cartridge TEXT,
                created_at TEXT NOT NULL
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS memory_units (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_type_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                key TEXT NOT NULL,
                value_json TEXT NOT NULL,
                summary_text TEXT,
                tags_json TEXT NOT NULL DEFAULT '[]',
                importance_weight REAL NOT NULL DEFAULT 1.0,
                confidence REAL NOT NULL DEFAULT 0.5,
                complexity_level INTEGER NOT NULL DEFAULT 0,
                is_permanent INTEGER NOT NULL DEFAULT 0,
                archived INTEGER NOT NULL DEFAULT 0,
                source_turn_id INTEGER,
                created_at TEXT NOT NULL,
                last_accessed TEXT NOT NULL,
                last_reinforced TEXT NOT NULL,
                access_count INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(source_turn_id) REFERENCES raw_turns(id)
            )
            """)

            cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_identity
            ON memory_units(subject, key)
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS memory_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id INTEGER,
                event_type TEXT NOT NULL,
                event_payload TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(memory_id) REFERENCES memory_units(id)
            )
            """)

            conn.commit()

    # ----------------------------
    # TURN LOGGING
    # ----------------------------
    def log_turn(
        self,
        user_message: str,
        assistant_message: str,
        previous_assistant_message: str = "",
        provider: str = "",
        model: str = "",
        cartridge: str = "",
    ) -> int:
        now = self._now()
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO raw_turns (
                    user_message,
                    assistant_message,
                    previous_assistant_message,
                    provider,
                    model,
                    cartridge,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                user_message,
                assistant_message,
                previous_assistant_message,
                provider,
                model,
                cartridge,
                now
            ))
            conn.commit()
            return cur.lastrowid

    def get_recent_turns(self, limit: int = 5) -> list[dict]:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT *
                FROM raw_turns
                ORDER BY id DESC
                LIMIT ?
            """, (limit,))
            return [dict(r) for r in cur.fetchall()]

    # ----------------------------
    # MEMORY PROCESSOR PROMPTING
    # ----------------------------
    def _memory_processor_system_prompt(self) -> str:
        return """
You are Sage's memory processor.

Your job is to analyze a user-assistant interaction and decide whether anything should be saved to long-term memory.

Only store memories if they are likely to matter later. Good candidates include:
- stable user preferences
- recurring goals
- project goals
- system architecture decisions
- long-term constraints
- important corrections
- durable workflow choices
- important factual state that will matter later

Do NOT store:
- filler
- greetings
- acknowledgments
- one-off small talk
- generic agreement
- duplicated trivial detail

If the user appears to be replying to a previous assistant response, analyze the relationship between:
- previous assistant message
- current user message
- current assistant message

Output JSON only.
No markdown.
No explanation.

Return this schema exactly:

{
  "should_store": true,
  "memory_type": "preference | project_goal | architecture_decision | constraint | workflow | identity | correction | fact | temporary_context",
  "subject": "user | sage | project | system",
  "key": "canonical.dot.key",
  "value_json": {},
  "summary_text": "short human-readable memory",
  "importance_weight": 0.0,
  "confidence": 0.0,
  "complexity_level": 0,
  "is_permanent": false,
  "tags": ["tag1", "tag2"]
}

Rules:
- should_store must be true or false
- key must be short, canonical, and machine-friendly
- importance_weight must be between 0.0 and 1.5
- confidence must be between 0.0 and 1.0
- complexity_level must be 0, 1, or 2
- tags must be short and useful
- if should_store is false, still return the schema, but use empty/neutral values
"""

    def _memory_processor_user_prompt(
        self,
        user_message: str,
        assistant_message: str,
        previous_assistant_message: str = "",
    ) -> str:
        payload = {
            "previous_assistant_message": previous_assistant_message or "",
            "user_message": user_message or "",
            "assistant_message": assistant_message or "",
        }
        return self._json_dumps(payload)

    def _call_memory_processor(
        self,
        user_message: str,
        assistant_message: str,
        previous_assistant_message: str = "",
    ) -> dict[str, Any]:
        prompt = self._memory_processor_user_prompt(
            user_message=user_message,
            assistant_message=assistant_message,
            previous_assistant_message=previous_assistant_message,
        )

        response = requests.post(
            f"{self.ollama_base_url}/api/chat",
            json={
                "model": self.memory_model,
                "messages": [
                    {"role": "system", "content": self._memory_processor_system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "format": "json",
                "options": {
                    "num_ctx": 1024,
                    "temperature": 0.1,
                },
            },
            timeout=180,
        )
        response.raise_for_status()
        data = response.json()
        content = data.get("message", {}).get("content", "").strip()

        # format: "json" should give us clean JSON, but fall back to extraction
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        parsed = self._extract_json_object(content)
        if not parsed:
            raise RuntimeError(f"Memory processor did not return valid JSON. Raw output: {content}")

        return parsed

    def _extract_json_object(self, text: str) -> Optional[dict[str, Any]]:
        # Try full parse first
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

        # Then attempt to slice first outer JSON object
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end + 1]
            try:
                obj = json.loads(candidate)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass

        return None

    # ----------------------------
    # CANDIDATE VALIDATION
    # ----------------------------
    def validate_candidate(self, candidate: dict[str, Any]) -> dict[str, Any]:
        cleaned = {
            "should_store": bool(candidate.get("should_store", False)),
            "memory_type": str(candidate.get("memory_type", "temporary_context")).strip(),
            "subject": str(candidate.get("subject", "user")).strip(),
            "key": str(candidate.get("key", "")).strip(),
            "value_json": candidate.get("value_json", {}),
            "summary_text": str(candidate.get("summary_text", "")).strip(),
            "importance_weight": float(candidate.get("importance_weight", 0.0) or 0.0),
            "confidence": float(candidate.get("confidence", 0.0) or 0.0),
            "complexity_level": int(candidate.get("complexity_level", 0) or 0),
            "is_permanent": bool(candidate.get("is_permanent", False)),
            "tags": candidate.get("tags", []),
        }

        if cleaned["memory_type"] not in self.MEMORY_TYPES:
            cleaned["memory_type"] = "temporary_context"

        if cleaned["subject"] not in {"user", "sage", "project", "system"}:
            cleaned["subject"] = "user"

        if not isinstance(cleaned["value_json"], dict):
            cleaned["value_json"] = {"value": str(cleaned["value_json"])}

        if not isinstance(cleaned["tags"], list):
            cleaned["tags"] = []

        cleaned["tags"] = [str(t).strip() for t in cleaned["tags"] if str(t).strip()]

        cleaned["importance_weight"] = max(0.0, min(cleaned["importance_weight"], 1.5))
        cleaned["confidence"] = max(0.0, min(cleaned["confidence"], 1.0))
        cleaned["complexity_level"] = max(0, min(cleaned["complexity_level"], 2))

        # Force discard if crucial fields missing
        if not cleaned["key"] or not cleaned["summary_text"]:
            cleaned["should_store"] = False

        return cleaned

    # ----------------------------
    # MEMORY UPSERT
    # ----------------------------
    def upsert_memory_candidate(
        self,
        candidate: dict[str, Any],
        source_turn_id: Optional[int] = None,
    ) -> Optional[int]:
        candidate = self.validate_candidate(candidate)

        if not candidate["should_store"]:
            return None

        now = self._now()
        memory_type_id = self.MEMORY_TYPES[candidate["memory_type"]]
        subject = candidate["subject"]
        key = candidate["key"]
        value_json = self._json_dumps(candidate["value_json"])
        summary_text = candidate["summary_text"]
        tags_json = self._json_dumps(candidate["tags"])
        importance_weight = candidate["importance_weight"]
        confidence = candidate["confidence"]
        complexity_level = candidate["complexity_level"]
        is_permanent = int(candidate["is_permanent"])

        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, importance_weight, access_count
                FROM memory_units
                WHERE subject = ? AND key = ?
            """, (subject, key))
            existing = cur.fetchone()

            if existing:
                new_weight = existing["importance_weight"] + importance_weight
                cur.execute("""
                    UPDATE memory_units
                    SET memory_type_id = ?,
                        value_json = ?,
                        summary_text = ?,
                        tags_json = ?,
                        importance_weight = ?,
                        confidence = MAX(confidence, ?),
                        complexity_level = ?,
                        is_permanent = MAX(is_permanent, ?),
                        archived = 0,
                        last_accessed = ?,
                        last_reinforced = ?,
                        access_count = access_count + 1
                    WHERE id = ?
                """, (
                    memory_type_id,
                    value_json,
                    summary_text,
                    tags_json,
                    new_weight,
                    confidence,
                    complexity_level,
                    is_permanent,
                    now,
                    now,
                    existing["id"],
                ))
                memory_id = existing["id"]
                event_type = "reinforce"
            else:
                cur.execute("""
                    INSERT INTO memory_units (
                        memory_type_id,
                        subject,
                        key,
                        value_json,
                        summary_text,
                        tags_json,
                        importance_weight,
                        confidence,
                        complexity_level,
                        is_permanent,
                        archived,
                        source_turn_id,
                        created_at,
                        last_accessed,
                        last_reinforced
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
                """, (
                    memory_type_id,
                    subject,
                    key,
                    value_json,
                    summary_text,
                    tags_json,
                    importance_weight,
                    confidence,
                    complexity_level,
                    is_permanent,
                    source_turn_id,
                    now,
                    now,
                    now,
                ))
                memory_id = cur.lastrowid
                event_type = "create"

            cur.execute("""
                INSERT INTO memory_events (memory_id, event_type, event_payload, created_at)
                VALUES (?, ?, ?, ?)
            """, (
                memory_id,
                event_type,
                self._json_dumps(candidate),
                now,
            ))
            conn.commit()

            return memory_id

    # ----------------------------
    # MAIN MEMORY ENTRYPOINT
    # ----------------------------
    def process_turn(
        self,
        user_message: str,
        assistant_message: str,
        previous_assistant_message: str = "",
        provider: str = "",
        model: str = "",
        cartridge: str = "",
        auto_maintain: bool = True,
    ) -> dict[str, Any]:
        """
        Full turn pipeline:
        1. log raw turn
        2. analyze with local memory processor
        3. validate/store candidate if relevant
        4. optionally decay/archive
        """
        turn_id = self.log_turn(
            user_message=user_message,
            assistant_message=assistant_message,
            previous_assistant_message=previous_assistant_message,
            provider=provider,
            model=model,
            cartridge=cartridge,
        )

        processor_output = self._call_memory_processor(
            user_message=user_message,
            assistant_message=assistant_message,
            previous_assistant_message=previous_assistant_message,
        )
        candidate = self.validate_candidate(processor_output)
        memory_id = self.upsert_memory_candidate(candidate, source_turn_id=turn_id)

        if auto_maintain:
            self.apply_decay(decay_factor=0.01)
            self.archive_weak_memories(threshold=0.08)

        return {
            "turn_id": turn_id,
            "candidate": candidate,
            "memory_id": memory_id,
        }

    # ----------------------------
    # RETRIEVAL
    # ----------------------------
    def retrieve_context(
        self,
        max_complexity: int = 2,
        limit: int = 12,
        include_archived: bool = False,
        query_text: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT *
                FROM memory_units
                WHERE complexity_level <= ?
            """, (max_complexity,))
            rows = [dict(r) for r in cur.fetchall()]

        if not include_archived:
            rows = [r for r in rows if not r["archived"]]

        if query_text:
            q = query_text.lower()
            scored = []
            for r in rows:
                score = float(r["importance_weight"])
                summary = (r.get("summary_text") or "").lower()
                key = (r.get("key") or "").lower()
                tags = " ".join(self._json_loads_safe(r.get("tags_json", "[]"), [])).lower()

                if q in summary:
                    score += 2.0
                if q in key:
                    score += 1.5
                if q in tags:
                    score += 1.0

                r["_retrieval_score"] = score
                scored.append((score, r))
            rows = [r for _, r in sorted(scored, key=lambda x: x[0], reverse=True)]
        else:
            rows.sort(key=lambda r: (r["importance_weight"], r["last_accessed"]), reverse=True)

        return rows[:limit]

    def build_prompt_memory_snippets(
        self,
        query_text: str,
        max_complexity: int = 2,
        limit: int = 8,
        min_score: float = 0.15,
    ) -> list[str]:
        memories = self.retrieve_context(
            max_complexity=max_complexity,
            limit=limit,
            query_text=query_text,
        )
        snippets = []
        for m in memories:
            # Skip low-relevance memories to reduce prompt bloat
            if m.get("_retrieval_score", 0) < min_score:
                continue

            summary = m.get("summary_text")
            if summary:
                snippets.append(f"[#{m['id']}] {summary}")

            self.touch_memory(m["id"])

        return snippets

    def touch_memory(self, memory_id: int):
        now = self._now()
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE memory_units
                SET last_accessed = ?, access_count = access_count + 1
                WHERE id = ?
            """, (now, memory_id))
            conn.commit()

    # ----------------------------
    # VIEW / EDIT
    # ----------------------------
    def view_memories(self, include_archived: bool = False, limit: int = 1000) -> list[dict[str, Any]]:
        memories = self.retrieve_context(
            max_complexity=99,
            limit=limit,
            include_archived=include_archived,
        )

        rendered = []
        for m in memories:
            rendered.append({
                "id": m["id"],
                "memory_type": self.REVERSE_MEMORY_TYPES.get(m["memory_type_id"], "unknown"),
                "subject": m["subject"],
                "key": m["key"],
                "value": self._json_loads_safe(m["value_json"], {}),
                "summary": m["summary_text"],
                "tags": self._json_loads_safe(m["tags_json"], []),
                "importance": m["importance_weight"],
                "confidence": m["confidence"],
                "complexity": m["complexity_level"],
                "permanent": bool(m["is_permanent"]),
                "archived": bool(m["archived"]),
                "created_at": m["created_at"],
                "last_accessed": m["last_accessed"],
            })
        return rendered

    def get_memory_by_id(self, memory_id: int) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT *
                FROM memory_units
                WHERE id = ?
            """, (memory_id,))
            row = cur.fetchone()
            if not row:
                return None
            m = dict(row)
            return {
                "id": m["id"],
                "memory_type": self.REVERSE_MEMORY_TYPES.get(m["memory_type_id"], "unknown"),
                "subject": m["subject"],
                "key": m["key"],
                "value_json": self._json_loads_safe(m["value_json"], {}),
                "summary_text": m["summary_text"],
                "tags": self._json_loads_safe(m["tags_json"], []),
                "importance_weight": m["importance_weight"],
                "confidence": m["confidence"],
                "complexity_level": m["complexity_level"],
                "is_permanent": bool(m["is_permanent"]),
                "archived": bool(m["archived"]),
            }

    def edit_memory_from_text(self, memory_id: int, edited_text: str) -> dict[str, Any]:
        """
        Converts user-edited natural language back into structured memory
        by asking the local memory processor to re-encode it.
        """
        existing = self.get_memory_by_id(memory_id)
        if not existing:
            raise ValueError(f"Memory id {memory_id} not found.")

        system_prompt = """
You are recompiling a human-edited memory back into Sage's structured memory format.

Return JSON only.
Use this schema exactly:

{
  "memory_type": "preference | project_goal | architecture_decision | constraint | workflow | identity | correction | fact | temporary_context",
  "subject": "user | sage | project | system",
  "key": "canonical.dot.key",
  "value_json": {},
  "summary_text": "short human-readable memory",
  "importance_weight": 0.0,
  "confidence": 0.0,
  "complexity_level": 0,
  "is_permanent": false,
  "tags": ["tag1", "tag2"]
}
"""

        user_prompt = self._json_dumps({
            "existing_memory": existing,
            "edited_text": edited_text,
        })

        response = requests.post(
            f"{self.ollama_base_url}/api/chat",
            json={
                "model": self.memory_model,
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
            timeout=180,
        )
        response.raise_for_status()
        data = response.json()
        content = data.get("message", {}).get("content", "").strip()

        try:
            candidate = json.loads(content)
            if not isinstance(candidate, dict):
                candidate = None
        except Exception:
            candidate = self._extract_json_object(content)
        if not candidate:
            raise RuntimeError("Could not parse edited memory into structured JSON.")

        candidate["should_store"] = True
        candidate = self.validate_candidate(candidate)
        self.update_memory_from_structured_edit(memory_id, candidate)
        return candidate

    def update_memory_from_structured_edit(self, memory_id: int, edited_candidate: dict[str, Any]):
        now = self._now()
        memory_type_id = self.MEMORY_TYPES[edited_candidate["memory_type"]]

        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE memory_units
                SET memory_type_id = ?,
                    subject = ?,
                    key = ?,
                    value_json = ?,
                    summary_text = ?,
                    tags_json = ?,
                    importance_weight = ?,
                    confidence = ?,
                    complexity_level = ?,
                    is_permanent = ?,
                    archived = 0,
                    last_accessed = ?,
                    last_reinforced = ?
                WHERE id = ?
            """, (
                memory_type_id,
                edited_candidate["subject"],
                edited_candidate["key"],
                self._json_dumps(edited_candidate["value_json"]),
                edited_candidate["summary_text"],
                self._json_dumps(edited_candidate["tags"]),
                float(edited_candidate["importance_weight"]),
                float(edited_candidate["confidence"]),
                int(edited_candidate["complexity_level"]),
                int(bool(edited_candidate["is_permanent"])),
                now,
                now,
                memory_id,
            ))

            cur.execute("""
                INSERT INTO memory_events (memory_id, event_type, event_payload, created_at)
                VALUES (?, ?, ?, ?)
            """, (
                memory_id,
                "manual_edit",
                self._json_dumps(edited_candidate),
                now,
            ))
            conn.commit()

    # ----------------------------
    # MAINTENANCE
    # ----------------------------
    def apply_decay(self, decay_factor: float = 0.03):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE memory_units
                SET importance_weight = MAX(0, importance_weight - ?)
                WHERE is_permanent = 0 AND archived = 0
            """, (decay_factor,))
            conn.commit()

    def archive_weak_memories(self, threshold: float = 0.15):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE memory_units
                SET archived = 1
                WHERE is_permanent = 0
                  AND archived = 0
                  AND importance_weight < ?
            """, (threshold,))
            conn.commit()

    def unarchive_memory(self, memory_id: int):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE memory_units
                SET archived = 0
                WHERE id = ?
            """, (memory_id,))
            conn.commit()

    def delete_memory(self, memory_id: int):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM memory_events WHERE memory_id = ?", (memory_id,))
            cur.execute("DELETE FROM memory_units WHERE id = ?", (memory_id,))
            conn.commit()


# ----------------------------
# SIMPLE TEST HARNESS
# ----------------------------
if __name__ == "__main__":
    import os as _os
    _state_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "sage_state")
    _os.makedirs(_state_dir, exist_ok=True)

    engine = MemoryEngine(
        db_path=_os.path.join(_state_dir, "brain_storage.db"),
        memory_model="gemma4:e2b",
    )

    result = engine.process_turn(
        user_message="I want Sage's model switching to feel like swapping game cartridges.",
        assistant_message="That suggests a cartridge-based model profile system with shared memory.",
        previous_assistant_message="We should separate identity from the active model.",
        provider="ollama",
        model="gemma4:26b",
        cartridge="local-default",
    )

    print("\nPROCESS RESULT:")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    print("\nVIEW MEMORIES:")
    for memory in engine.view_memories(include_archived=True):
        print(json.dumps(memory, indent=2, ensure_ascii=False))