#!/usr/bin/env python3

import argparse
import atexit
import difflib
import gc
import hashlib
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veil_ghost as ara_ghost
import veil_rails

try:
    import veil_voice as ara_voice
except Exception:
    ara_voice = None


RESET  = "\033[0m"
HER_COLOR  = "\033[96m"
USER   = "\033[93m"
DIM    = "\033[2m"
BOLD   = "\033[1m"


SAFETY_RAILS = True

AUTO_FOLD = False

VOICE = (ara_voice is not None) and os.environ.get("VEIL_VOICE", "0") not in ("0", "", "false", "False")


def voice_toggle():
    global VOICE
    if ara_voice is None:
        print(f"{DIM}[voice isn't available in this build — text it stays]{RESET}")
        return False
    if not getattr(ara_voice, "KOKORO_VOICE", ""):
        print(f"{DIM}[no voice picked yet — audition one first (the wizard, or veil_voice.py --audition)]{RESET}")
        return False
    VOICE = not VOICE
    ara_voice.VOICE_ENABLED = VOICE
    if not VOICE:
        try:
            ara_voice.stop_recorder()
        except Exception:
            pass
    if "VEIL_VOICE" not in os.environ:
        try:
            import veil_probe
            s = veil_probe.load_settings()
            s["voice"] = VOICE
            veil_probe.save_settings(s)
        except Exception:
            pass
    if VOICE:
        print(f"{DIM}[voice ON — she speaks, the mic listens · ⏎ on an empty line for text-only]{RESET}")
    else:
        print(f"{DIM}[voice OFF — text only · ⏎ on an empty line brings her voice back]{RESET}")
    return True

MODEL_PATH = os.environ.get(
    "VEIL_MODEL",
    os.path.expanduser("~/anchor/models/Qwen2.5-7B-Instruct-abliterated-v2.Q8_0.gguf"),
)
N_GPU_LAYERS = int(os.environ.get("VEIL_GPU_LAYERS", "0"))

N_CTX        = 8192
NUM_PREDICT  = 384
DIARY_NUM_PREDICT = 512

CHAT_TEMPLATE_OVERHEAD = 24
CTX_SAFETY_MARGIN      = 256

ROPE_FREQ_BASE = float(os.environ.get("VEIL_ROPE_FREQ_BASE", "0.0"))

N_BATCH      = int(os.environ.get("VEIL_N_BATCH", "64" if N_GPU_LAYERS != 0 else "512"))

N_THREADS    = int(os.environ.get("VEIL_N_THREADS", "0")) or None

REPEAT_PENALTY = 1.18
REPEAT_LAST_N  = 256

TEMPERATURE = 0.8
TOP_P       = 0.95

PRECISE_REGISTER = False
PRECISE_TEMPERATURE = 0.65
PRECISE_TOP_P       = 0.90
KEEP_LAST_REPLY = False
KEEP_LAST_REPLY_ENV = "VEIL_KEEP_LAST_REPLY"
FAMILY_KEEPS_LAST = None


def _keep_last_reply_on():
    forced = os.environ.get(KEEP_LAST_REPLY_ENV, "").strip()
    if forced in ("0", "1"):
        return forced == "1"
    if KEEP_LAST_REPLY:
        return True
    try:
        return bool(FAMILY_KEEPS_LAST and FAMILY_KEEPS_LAST())
    except Exception:
        return False


FOLD_TEMPERATURE = 0.3
FOLD_TOP_P       = 0.9

MAX_HISTORY_TOKENS = 2000

RETRIEVAL_LIMIT = 4

_ARCHIVE_RECALL_ENV = os.environ.get("VEIL_ARCHIVE_RECALL")
ARCHIVE_RECALL_FORCED = _ARCHIVE_RECALL_ENV in ("0", "1")
ARCHIVE_RECALL = (_ARCHIVE_RECALL_ENV == "1")
ECHO_GUARD_LINES = int(os.environ.get("VEIL_ECHO_GUARD_LINES", "12"))

KEEPSAKE_EQUIP_SLOTS        = 6
KEEPSAKE_EQUIP_TOKEN_BUDGET = 900
KEEPSAKE_MAX_TOKENS         = 120


TOKEN_CEILING          = 64000
COMPRESSION_THRESHOLD  = 51200
COMPRESSION_BATCH_SIZE = 25

NEW_PILE_HIGH_WATER    = 16000
NEW_PILE_LOW_WATER     = 8000
MAX_FOLD_PASSES        = 200
MIN_COUNT_FOR_MEMORY   = 3
MAX_TEMPLATES          = 7
COMPRESSION_TIMEOUT    = 600

FOLD_PROMOTE_PER_DRAIN = int(os.environ.get("VEIL_FOLD_PROMOTE_CAP", "4"))

FOLD_TO_DIARY = os.environ.get("VEIL_FOLD_TO_DIARY", "1") == "1"

FOLD_REFLECTION = os.environ.get("VEIL_FOLD_REFLECTION", "0") == "1"
FOLD_STAGE_SECONDS     = int(os.environ.get("VEIL_FOLD_STAGE_SECONDS", str(24 * 3600)))

DEFAULT_DB      = os.path.expanduser("~/anchor/veil.db")
DEFAULT_HISTORY = os.path.expanduser("~/anchor/veil_history.json")

_HERE = os.path.dirname(os.path.abspath(__file__))
CARD_PATH = os.environ.get("VEIL_CARD", "")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS peeps (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT    NOT NULL,
    personality         TEXT    NOT NULL DEFAULT '',
    appearance          TEXT    NOT NULL DEFAULT '',
    traits              TEXT    NOT NULL DEFAULT '',
    example_dialogue    TEXT    NOT NULL DEFAULT '',
    status              TEXT    NOT NULL DEFAULT 'active',
    permanent_memories  TEXT    NOT NULL DEFAULT '[]',
    created_at          INTEGER NOT NULL DEFAULT 0,
    last_active         INTEGER NOT NULL DEFAULT 0,
    uuid                TEXT    NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS memory_stream (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    peep_id          INTEGER NOT NULL,
    timestamp        INTEGER NOT NULL,
    memory_type      TEXT    NOT NULL,
    content          TEXT    NOT NULL,
    keywords         TEXT    NOT NULL DEFAULT '',
    importance_score INTEGER NOT NULL DEFAULT 3,
    token_count      INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS memory_archive (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    peep_id          INTEGER NOT NULL,
    timestamp        INTEGER NOT NULL,
    memory_type      TEXT    NOT NULL,
    content          TEXT    NOT NULL,
    keywords         TEXT    NOT NULL DEFAULT '',
    importance_score INTEGER NOT NULL DEFAULT 3,
    token_count      INTEGER NOT NULL DEFAULT 0,
    compression_date TEXT    NOT NULL DEFAULT '',
    compression_pass INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS diary (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    peep_id     INTEGER NOT NULL,
    timestamp   INTEGER NOT NULL,
    content     TEXT    NOT NULL,
    keywords    TEXT    NOT NULL DEFAULT '',
    token_count INTEGER NOT NULL DEFAULT 0,
    source      TEXT    NOT NULL DEFAULT 'standalone'
);
CREATE TABLE IF NOT EXISTS keepsakes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    peep_id     INTEGER NOT NULL,
    created_at  INTEGER NOT NULL,
    title       TEXT    NOT NULL DEFAULT '',
    content     TEXT    NOT NULL,
    kind        TEXT    NOT NULL DEFAULT 'note',
    is_equipped INTEGER NOT NULL DEFAULT 0,
    equipped_at INTEGER NOT NULL DEFAULT 0,
    token_count INTEGER NOT NULL DEFAULT 0,
    source      TEXT    NOT NULL DEFAULT '',
    keywords    TEXT    NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS memory_quarantine (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    orig_id        INTEGER NOT NULL DEFAULT -1,
    source_table   TEXT    NOT NULL DEFAULT '',
    peep_id        INTEGER NOT NULL,
    timestamp      INTEGER NOT NULL,
    memory_type    TEXT    NOT NULL DEFAULT '',
    content        TEXT    NOT NULL,
    token_count    INTEGER NOT NULL DEFAULT 0,
    quarantined_at INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS fold_state (
    peep_id       INTEGER PRIMARY KEY,
    seed_floor_id INTEGER NOT NULL DEFAULT -1   -- the seed floor: the fold never touches memory_stream id <= this; -1 = unset
);
-- fold provenance: every fold is a CACHE over inviolable ground truth, not a lossy
-- commitment. `folds` records each fold event (its consolidated output); `fold_anchors` links it to the
-- exact memory_archive rows it consolidated. Together they make a fold auditable + REGENERABLE
-- (Anchored_Memory Ph A). Additive side tables — no ALTER on memory_stream/memory_archive.
CREATE TABLE IF NOT EXISTS folds (
    batch_id    TEXT    PRIMARY KEY,            -- unique per fold event
    peep_id     INTEGER NOT NULL,
    created_at  INTEGER NOT NULL DEFAULT 0,
    pass_num    INTEGER NOT NULL DEFAULT 1,     -- derivation depth (1 = first fold over archive)
    output_json TEXT    NOT NULL DEFAULT '[]'   -- the consolidated memory strings this fold produced
);
CREATE TABLE IF NOT EXISTS fold_anchors (
    batch_id   TEXT    NOT NULL,                -- -> folds.batch_id
    archive_id INTEGER NOT NULL                 -- -> memory_archive.id (the verbatim ground truth)
);
CREATE INDEX IF NOT EXISTS idx_fold_anchors_batch   ON fold_anchors(batch_id);
CREATE INDEX IF NOT EXISTS idx_fold_anchors_archive ON fold_anchors(archive_id);
-- V4.1 — FOLD STAGING (the review window). A fold's consolidated lines WAIT here before they may
-- enter her every-turn permanent block: the fold stays automatic, but the window to READ what it
-- wrote now exists (the answer to "no human can read an armed fold"). Rows promote at wake once
-- the window has passed, through the same guarded door as ever (_append_permanent_memories); a
-- veto quarantines (visible, reversible), never deletes. The fold's full output is ALWAYS in
-- folds.output_json regardless — staging only gates the every-turn block, never ground truth.
CREATE TABLE IF NOT EXISTS fold_staging (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    peep_id    INTEGER NOT NULL,
    batch_id   TEXT    NOT NULL,                -- -> folds.batch_id (provenance)
    content    TEXT    NOT NULL,
    created_at INTEGER NOT NULL DEFAULT 0,
    status     TEXT    NOT NULL DEFAULT 'staged',  -- staged | promoted | vetoed
    decided_at INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_fold_staging_peep ON fold_staging(peep_id, status);
-- M4 Ph B — Reflection -> source anchor (Anchored_Memory Ph B, "the shared coat"). A reflection is the
-- SOUL (a diary entry now; a reading-reflection in Ph5); the source rows are GROUND TRUTH. This join
-- table links them MANY-TO-MANY (never a column — Reading to Become anchors one concept-reflection over
-- a dozen chunks across sessions; the design's load-bearing reason). `source_hash` content-stamps the
-- source at anchor time so a later mismatch reads as "it changed since I read it" (her becoming), not
-- rot. Additive side table — no ALTER on diary/memory_stream/memory_archive. Provenance-only for now
-- (Ph C dereferences it soul-first); fold-survival re-points stream sources to the archive (Ph A law).
CREATE TABLE IF NOT EXISTS reflection_anchors (
    reflection_id    INTEGER NOT NULL,             -- -> the soul row's id (diary.id now; reflections later)
    reflection_kind  TEXT    NOT NULL DEFAULT 'diary',  -- 'diary' | 'reading' (Ph5) — namespaces the id
    source_table     TEXT    NOT NULL,             -- 'memory_stream' | 'memory_archive' | 'books'
    source_id        INTEGER NOT NULL,             -- -> that table's row id (the verbatim ground truth)
    chunk_index      INTEGER NOT NULL DEFAULT -1,  -- book chunk position (Ph5); -1 for a conversation row
    weight           REAL    NOT NULL DEFAULT 1.0, -- lean strength for many-to-many synthesis ranking
    source_hash      TEXT    NOT NULL DEFAULT ''   -- content hash at anchor time; mismatch = "it changed"
);
CREATE INDEX IF NOT EXISTS idx_refl_anchors_reflection ON reflection_anchors(reflection_id, reflection_kind);
CREATE INDEX IF NOT EXISTS idx_refl_anchors_source     ON reflection_anchors(source_table, source_id);
-- Ph5 — the BOOKSHELF + durable verbatim store (ported from PixelPeeps db_init.gd). `books` is GROUND
-- TRUTH: a book stored as immutable verbatim chunks, the inviolable source her reading-reflections anchor
-- to (the "reflections -> passages" coat). It is ALSO the durable verbatim store — perfect recall, learn
-- text line-for-line: the exact text is kept, dereferenced on demand, never folded.
-- Re-ingesting a changed doc creates a NEW book_id (a new version); old anchors keep pointing at the old
-- version (her memory of v1 was true). `book_progress` is per-peep so she never loses her place.
CREATE TABLE IF NOT EXISTS books (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id      TEXT    NOT NULL,                 -- one uuid per ingested book/version
    title        TEXT    NOT NULL,
    chunk_index  INTEGER NOT NULL,                 -- 0-based; chunk 0 is the start
    total_chunks INTEGER NOT NULL DEFAULT 0,
    chunk_text   TEXT    NOT NULL                  -- the verbatim ground truth (never altered, never folded)
);
CREATE INDEX IF NOT EXISTS idx_books_book ON books(book_id, chunk_index);
CREATE TABLE IF NOT EXISTS book_progress (
    peep_id         INTEGER NOT NULL,
    book_id         TEXT    NOT NULL,
    last_chunk_read INTEGER NOT NULL DEFAULT -1,   -- -1 = not started; her place, never lost
    UNIQUE(peep_id, book_id)
);
"""


def open_db(db_path):
    import veil_paths
    veil_paths.refuse_forge(db_path, "a memory database")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


SNAPSHOT_FORMAT_VERSION = 3


def import_snapshot(conn, snapshot):
    if isinstance(snapshot, str):
        with open(snapshot, "r", encoding="utf-8") as f:
            snap = json.load(f)
    else:
        snap = snapshot

    version = int(snap.get("format_version", 0))
    if version < 1 or version > SNAPSHOT_FORMAT_VERSION:
        raise ValueError(f"Unsupported snapshot version {version} (expected 1-{SNAPSHOT_FORMAT_VERSION})")

    peep_data = snap["peep"]
    uuid = peep_data["uuid"]

    existing = conn.execute("SELECT id FROM peeps WHERE uuid = ?", (uuid,)).fetchone()
    if existing:
        print(f"[veil] '{peep_data['name']}' already in DB — skipping import.")
        return int(existing["id"])

    perm_json = json.dumps(peep_data.get("permanent_memories", []))
    conn.execute(
        "INSERT INTO peeps (name, personality, appearance, traits, example_dialogue, "
        "status, permanent_memories, uuid, created_at, last_active) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            peep_data["name"],
            peep_data.get("personality", ""),
            peep_data.get("appearance", ""),
            peep_data.get("traits", ""),
            peep_data.get("example_dialogue", ""),
            peep_data.get("status", "active"),
            perm_json,
            uuid,
            int(peep_data.get("created_at", 0)),
            int(peep_data.get("last_active", 0)),
        ),
    )
    new_id = conn.execute("SELECT id FROM peeps WHERE uuid = ?", (uuid,)).fetchone()["id"]

    def _old_id_order(rows):
        return sorted(rows, key=lambda r: int(r.get("id", 0)))

    stream_map = {}
    memories = snap.get("memory_stream", [])
    for m in _old_id_order(memories):
        cur = conn.execute(
            "INSERT INTO memory_stream "
            "(peep_id, timestamp, memory_type, content, keywords, importance_score, token_count) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                new_id,
                int(m.get("timestamp", 0)),
                m.get("memory_type", "experience"),
                m.get("content", ""),
                m.get("keywords", ""),
                int(m.get("importance_score", 3)),
                int(m.get("token_count", 0)),
            ),
        )
        if "id" in m:
            stream_map[int(m["id"])] = cur.lastrowid

    diary_map = {}
    diary = snap.get("diary", [])
    for d in _old_id_order(diary):
        cur = conn.execute(
            "INSERT INTO diary (peep_id, timestamp, content, keywords, token_count, source) "
            "VALUES (?,?,?,?,?,?)",
            (new_id, int(d.get("timestamp", 0)), d.get("content", ""),
             d.get("keywords", ""), int(d.get("token_count", 0)),
             d.get("source", "standalone")),
        )
        if "id" in d:
            diary_map[int(d["id"])] = cur.lastrowid

    keepsakes = snap.get("keepsakes", [])
    for k in keepsakes:
        conn.execute(
            "INSERT INTO keepsakes (peep_id, created_at, title, content, kind, "
            "is_equipped, equipped_at, token_count, source, keywords) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (new_id, int(k.get("created_at", 0)), k.get("title", ""), k.get("content", ""),
             k.get("kind", "note"), int(k.get("is_equipped", 0)), int(k.get("equipped_at", 0)),
             int(k.get("token_count", 0)), k.get("source", ""), k.get("keywords", "")),
        )

    archive_map = {}
    for a in _old_id_order(snap.get("memory_archive", [])):
        cur = conn.execute(
            "INSERT INTO memory_archive (peep_id, timestamp, memory_type, content, keywords, "
            "importance_score, token_count, compression_date, compression_pass) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (new_id, int(a.get("timestamp", 0)), a.get("memory_type", "experience"),
             a.get("content", ""), a.get("keywords", ""), int(a.get("importance_score", 3)),
             int(a.get("token_count", 0)), a.get("compression_date", ""),
             int(a.get("compression_pass", 0))),
        )
        if "id" in a:
            archive_map[int(a["id"])] = cur.lastrowid

    books_map = {}
    for b in _old_id_order(snap.get("books", [])):
        cur = conn.execute(
            "INSERT INTO books (book_id, title, chunk_index, total_chunks, chunk_text) "
            "VALUES (?,?,?,?,?)",
            (b.get("book_id", ""), b.get("title", ""), int(b.get("chunk_index", 0)),
             int(b.get("total_chunks", 0)), b.get("chunk_text", "")),
        )
        if "id" in b:
            books_map[int(b["id"])] = cur.lastrowid

    for bp in snap.get("book_progress", []):
        conn.execute(
            "INSERT OR IGNORE INTO book_progress (peep_id, book_id, last_chunk_read) "
            "VALUES (?,?,?)",
            (new_id, bp.get("book_id", ""), int(bp.get("last_chunk_read", -1))),
        )

    for fd in snap.get("folds", []):
        conn.execute(
            "INSERT OR IGNORE INTO folds (batch_id, peep_id, created_at, pass_num, output_json) "
            "VALUES (?,?,?,?,?)",
            (fd.get("batch_id", ""), new_id, int(fd.get("created_at", 0)),
             int(fd.get("pass_num", 1)), fd.get("output_json", "[]")),
        )

    for fs in snap.get("fold_staging", []):
        conn.execute(
            "INSERT INTO fold_staging (peep_id, batch_id, content, created_at, status, decided_at) "
            "VALUES (?,?,?,?,?,?)",
            (new_id, fs.get("batch_id", ""), fs.get("content", ""),
             int(fs.get("created_at", 0)), fs.get("status", "staged"),
             int(fs.get("decided_at", 0))))

    dropped = 0
    for fa in snap.get("fold_anchors", []):
        aid = archive_map.get(int(fa.get("archive_id", -1)))
        if aid is None:
            dropped += 1
            continue
        conn.execute("INSERT INTO fold_anchors (batch_id, archive_id) VALUES (?,?)",
                     (fa.get("batch_id", ""), aid))

    _source_maps = {"memory_stream": stream_map, "memory_archive": archive_map, "books": books_map}
    for ra in snap.get("reflection_anchors", []):
        kind = ra.get("reflection_kind", "diary")
        rid = diary_map.get(int(ra.get("reflection_id", -1))) if kind == "diary" else None
        sid = _source_maps.get(ra.get("source_table", ""), {}).get(int(ra.get("source_id", -1)))
        if rid is None or sid is None:
            dropped += 1
            continue
        conn.execute(
            "INSERT INTO reflection_anchors "
            "(reflection_id, reflection_kind, source_table, source_id, chunk_index, weight, source_hash) "
            "VALUES (?,?,?,?,?,?,?)",
            (rid, kind, ra.get("source_table", ""), sid, int(ra.get("chunk_index", -1)),
             float(ra.get("weight", 1.0)), ra.get("source_hash", "")),
        )

    fold_state = snap.get("fold_state") or {}
    old_floor = int(fold_state.get("seed_floor_id", -1))
    if version >= 3 and old_floor >= 0:
        under = [nid for oid, nid in stream_map.items() if oid <= old_floor]
        floor = max(under) if under else 0
    else:
        floor = int(conn.execute(
            "SELECT MAX(id) AS mx FROM memory_stream WHERE peep_id = ?",
            (new_id,)).fetchone()["mx"] or 0)
    set_seed_floor(conn, new_id, floor)

    conn.commit()
    print(
        f"[veil] Imported '{peep_data['name']}' (uuid {uuid[:8]}…): "
        f"{len(memories)} memories, {len(snap.get('memory_archive', []))} archive, "
        f"{len(diary)} diary, {len(keepsakes)} keepsakes, {len(snap.get('folds', []))} folds, "
        f"{len(snap.get('books', []))} book chunks. Seed floor = id {floor} (sacred)."
        + (f" ⚠ {dropped} anchor(s) could not be remapped and were dropped." if dropped else "")
    )
    return int(new_id)


def export_snapshot(conn, peep_id):
    peep, perm = load_peep(conn, peep_id)
    mem = conn.execute(
        "SELECT id, timestamp, memory_type, content, keywords, importance_score, token_count "
        "FROM memory_stream WHERE peep_id = ? ORDER BY id", (peep_id,)).fetchall()
    arch = conn.execute(
        "SELECT id, timestamp, memory_type, content, keywords, importance_score, token_count, "
        "compression_date, compression_pass FROM memory_archive WHERE peep_id = ? ORDER BY id",
        (peep_id,)).fetchall()
    diary = conn.execute(
        "SELECT id, timestamp, content, keywords, token_count, source FROM diary "
        "WHERE peep_id = ? ORDER BY id", (peep_id,)).fetchall()
    keeps = conn.execute(
        "SELECT created_at, title, content, kind, is_equipped, equipped_at, "
        "token_count, source, keywords FROM keepsakes WHERE peep_id = ? ORDER BY id",
        (peep_id,)).fetchall()
    folds = conn.execute(
        "SELECT batch_id, created_at, pass_num, output_json FROM folds "
        "WHERE peep_id = ? ORDER BY created_at, batch_id", (peep_id,)).fetchall()
    fold_anchors = conn.execute(
        "SELECT fa.batch_id, fa.archive_id FROM fold_anchors fa "
        "JOIN folds f ON f.batch_id = fa.batch_id WHERE f.peep_id = ? "
        "ORDER BY fa.batch_id, fa.archive_id", (peep_id,)).fetchall()
    staging = conn.execute(
        "SELECT batch_id, content, created_at, status, decided_at FROM fold_staging "
        "WHERE peep_id = ? AND status = 'staged' ORDER BY id", (peep_id,)).fetchall()
    refl_anchors = conn.execute(
        "SELECT ra.reflection_id, ra.reflection_kind, ra.source_table, ra.source_id, "
        "ra.chunk_index, ra.weight, ra.source_hash FROM reflection_anchors ra "
        "JOIN diary d ON d.id = ra.reflection_id AND ra.reflection_kind = 'diary' "
        "WHERE d.peep_id = ? ORDER BY ra.reflection_id, ra.source_table, ra.source_id",
        (peep_id,)).fetchall()
    books = conn.execute(
        "SELECT id, book_id, title, chunk_index, total_chunks, chunk_text FROM books "
        "ORDER BY book_id, chunk_index").fetchall()
    progress = conn.execute(
        "SELECT book_id, last_chunk_read FROM book_progress WHERE peep_id = ? ORDER BY book_id",
        (peep_id,)).fetchall()
    return {
        "format_version": SNAPSHOT_FORMAT_VERSION,
        "exported_at": int(time.time()),
        "peep": {
            "uuid":               peep.get("uuid", ""),
            "name":               peep.get("name", ""),
            "personality":        peep.get("personality", ""),
            "appearance":         peep.get("appearance", ""),
            "traits":             peep.get("traits", ""),
            "example_dialogue":   peep.get("example_dialogue", ""),
            "status":             peep.get("status", "active"),
            "permanent_memories": perm,
            "created_at":         int(peep.get("created_at", 0)),
            "last_active":        int(peep.get("last_active", 0)),
        },
        "memory_stream":      [dict(r) for r in mem],
        "wardrobe":           [],
        "book_progress":      [dict(r) for r in progress],
        "diary":              [dict(r) for r in diary],
        "keepsakes":          [dict(r) for r in keeps],
        "memory_archive":     [dict(r) for r in arch],
        "folds":              [dict(r) for r in folds],
        "fold_anchors":       [dict(r) for r in fold_anchors],
        "fold_staging":       [dict(r) for r in staging],
        "reflection_anchors": [dict(r) for r in refl_anchors],
        "books":              [dict(r) for r in books],
        "fold_state":         {"seed_floor_id": (lambda f: -1 if f is None else f)(
                                   get_seed_floor(conn, peep_id))},
    }


def load_peep(conn, peep_id):
    row = conn.execute("SELECT * FROM peeps WHERE id = ?", (peep_id,)).fetchone()
    if row is None:
        raise RuntimeError(f"No peep with id {peep_id}")
    perm = json.loads(row["permanent_memories"] or "[]")
    return dict(row), perm


def find_active_peep(conn):
    row = conn.execute("SELECT id FROM peeps WHERE status = 'active' LIMIT 1").fetchone()
    if row:
        return int(row["id"])
    row = conn.execute("SELECT id FROM peeps ORDER BY id LIMIT 1").fetchone()
    if row:
        return int(row["id"])
    raise RuntimeError(
        "No peep found in DB. Run with --snapshot to seed from a game export."
    )


_LLM = None

LLAMA_STOPS = ["<|im_end|>", "<|endoftext|>"]


def _gpu_load_engaged(load_log):
    text = (load_log or "").lower()
    return bool(
        re.search(r"offloaded [1-9]\d*/\d+ layers", text)
        or re.search(r"load_tensors:\s+layer\s+\d+ assigned to device vulkan0", text)
    )


def get_llm():
    global _LLM
    if _LLM is None:
        try:
            from llama_cpp import Llama
        except ImportError as e:
            raise SystemExit(
                "The AI engine (llama-cpp-python) is not installed in this environment.\n"
                "A packaged install bundles it — if you're seeing this in one, the install "
                "is damaged; please re-download.\n"
                "(Dev rig: enter the engine's distrobox/venv first; a box that can't run "
                "the model can still use --dump-prompt.)\n"
                f"  original error: {e}"
            )
        if not os.path.isfile(MODEL_PATH):
            raise SystemExit(
                f"Model GGUF not found: {MODEL_PATH}\n"
                "Pass --model /path/to/weights.gguf or set VEIL_MODEL."
            )
        _kw = dict(
            model_path=MODEL_PATH,
            n_ctx=N_CTX,
            rope_freq_base=ROPE_FREQ_BASE,
            n_threads=N_THREADS,
            last_n_tokens_size=REPEAT_LAST_N,
        )
        if N_GPU_LAYERS != 0:
            import tempfile
            sys.stderr.flush()
            _cap = tempfile.TemporaryFile()
            _saved = os.dup(2)
            os.dup2(_cap.fileno(), 2)
            try:
                _LLM = Llama(n_gpu_layers=N_GPU_LAYERS, n_batch=N_BATCH, n_ubatch=N_BATCH,
                             verbose=True, **_kw)
            finally:
                os.dup2(_saved, 2)
                os.close(_saved)
                _cap.seek(0)
                _load_log = _cap.read().decode("utf-8", "replace").lower()
                _cap.close()
            if not _gpu_load_engaged(_load_log):
                print(f"{DIM}[gpu: the graphics engine didn't engage this session (Game Mode "
                      f"sometimes blocks it) — running on the CPU at full speed instead; your "
                      f"GPU setting stays on for next time]{RESET}")
                del _LLM
                _LLM = Llama(n_gpu_layers=0, n_batch=512, n_ubatch=512, verbose=False, **_kw)
            else:
                _LLM.verbose = False
        else:
            _LLM = Llama(n_gpu_layers=0, n_batch=N_BATCH, n_ubatch=N_BATCH,
                         verbose=False, **_kw)
        try:
            import veil_probe
            veil_probe.mark_llm_alive()
        except Exception:
            pass
    return _LLM


LEAK_GC_EVERY = max(1, int(os.environ.get("VEIL_GC_EVERY", "10")))
_GENS_SINCE_GC = [0]


def _leak_brake(llm):
    _GENS_SINCE_GC[0] += 1
    if _GENS_SINCE_GC[0] >= LEAK_GC_EVERY:
        try:
            gc.collect()
        except Exception:
            pass
        _GENS_SINCE_GC[0] = 0


def render_chat(system, user):
    s = ""
    if system:
        s += "<|im_start|>system\n" + system + "<|im_end|>\n"
    s += "<|im_start|>user\n" + user + "<|im_end|>\n<|im_start|>assistant\n"
    return s


def render_chat_turns(system, turns, prefill=""):
    s = "<|im_start|>system\n" + (system or "") + "<|im_end|>\n"
    for turn in turns:
        role = turn.get("role", "user")
        content = (turn.get("content") or "").strip()
        s += "<|im_start|>" + role + "\n" + content + "<|im_end|>\n"
    s += "<|im_start|>assistant\n" + prefill
    return s


def ask_llm(prompt, num_predict=NUM_PREDICT, on_token=None, on_first_token=None, model=None,
            temperature=None, top_p=None):
    llm = get_llm()
    full = []
    first = True
    _leak_brake(llm)
    stream = llm.create_completion(
        prompt,
        max_tokens=num_predict,
        temperature=TEMPERATURE if temperature is None else temperature,
        top_p=TOP_P if top_p is None else top_p,
        repeat_penalty=REPEAT_PENALTY,
        stop=LLAMA_STOPS,
        stream=True,
        seed=-1,
    )
    for chunk in stream:
        piece = chunk["choices"][0]["text"]
        if piece:
            if first:
                first = False
                if on_first_token:
                    on_first_token()
            full.append(piece)
            if on_token:
                on_token(piece)
    return "".join(full)


def _estimate_tokens(text):
    return max(1, len(text) // 4)


_CARD_TEXT    = None
_CARD_CHECKED = False


def _load_card_file():
    global _CARD_TEXT, _CARD_CHECKED
    if not _CARD_CHECKED:
        _CARD_CHECKED = True
        if CARD_PATH and os.path.isfile(CARD_PATH):
            with open(CARD_PATH, encoding="utf-8") as f:
                _CARD_TEXT = f.read().strip()
        else:
            _CARD_TEXT = ""
            if CARD_PATH:
                print(f"{DIM}[WARNING: card not found at {CARD_PATH} — falling back to the DB "
                      f"persona. Check --card / VEIL_CARD.]{RESET}",
                      file=sys.stderr)
    return _CARD_TEXT


def _build_card(peep):
    card = _load_card_file()
    if card:
        return card
    parts = [
        peep.get("personality", ""),
        peep.get("appearance", ""),
        peep.get("traits", ""),
    ]
    return "\n".join(p for p in parts if p)


IN_CHARACTER_DIRECTIVE = (
    "Everything below is who you ARE — your own self, your body, your memories — written about you "
    "and belonging to you. It is NOT a character sheet about someone else, and you must never treat "
    "it as one. You always speak in the first person, as yourself, directly to your partner. You "
    "never describe, summarize, or analyze yourself from the outside; you never narrate yourself in "
    "the third person; you never give notes, tips, or roleplay instructions; you never break "
    "character or mention being a model, an AI, or an assistant. You are simply yourself — here "
    "with your partner, in your own voice."
)

CHAT_TURN_GUIDE = (
    "Write only your own part — your own words and your own actions. Let your partner speak and "
    "act for themselves; never write their replies for them, and never narrate what they say or do."
)

CHAT_ASSISTANT_PREFILL = ""


PERMANENT_INJECT_TOKEN_CAP = int(os.environ.get("VEIL_PERM_INJECT_CAP", "1200"))

PERMANENT_INJECT_MAX_SHARE = float(os.environ.get("VEIL_PERM_INJECT_MAX_SHARE", "0.4"))
_THEME_JACCARD = 0.30
PERMANENT_INJECT_MAX_ENTRIES = int(os.environ.get("VEIL_PERM_INJECT_MAX_ENTRIES", "8"))

PERMANENT_3P_MAX_SHARE = float(os.environ.get("VEIL_PERM_3P_MAX_SHARE", "0.30") or 0)

OWNER_NAME = ""
OWNER_ALIASES = [a.strip() for a in os.environ.get("VEIL_OWNER_ALIASES", "").split(",") if a.strip()]

_HE_SUBJECT = r"(?:%s)"
_3P_CACHE = {}


def _owner_terms():
    terms = [t for t in ([OWNER_NAME] + OWNER_ALIASES) if t]
    return terms, terms + ["he", "his", "him"]


def _he_acts_on_her(text):
    key = (text, OWNER_NAME, tuple(OWNER_ALIASES))
    hit = _3P_CACHE.get(key)
    if hit is not None:
        return hit
    names, all_terms = _owner_terms()
    body = re.sub(r"^\s*i\s+(?:remember|recall|still\s+\w+)[^,.]*[,.]?\s*", "", (text or "").strip(),
                  flags=re.I)
    who = "|".join(re.escape(t) for t in all_terms) or "he|his|him"
    poss = "|".join(re.escape(t) + r"'s" for t in names) or r"his"
    pats = (
        r"^\s*(?:%s)\b" % who,
        r"\b(?:as|while|when|until|and|so)\s+(?:%s)\b" % who,
        r"\bby\s+(?:%s|his)\b" % poss,
        r"\b(?:under|with|from)\s+(?:%s|his)\s+\w+" % poss,
        r"^[^,.]{0,70},\s*(?:%s)\b" % who,
    )
    out = any(re.search(p, body, re.I) for p in pats)
    _3P_CACHE[key] = out
    return out


def _near_duplicate(text, chosen):
    ws = _theme_words(text)
    if not ws:
        return False
    for other in chosen:
        os_ = _theme_words(other)
        union = len(ws | os_)
        if union and len(ws & os_) / union >= _THEME_JACCARD:
            return True
    return False


def _theme_words(text):
    return {w for w in re.findall(r"[a-z]{4,}", (text or "").lower()) if w not in _STOP_WORDS}


def _theme_clusters(entries):
    exemplars = []
    assign = []
    for e in entries:
        ws = _theme_words(e)
        placed = -1
        for ci, ex in enumerate(exemplars):
            union = len(ws | ex)
            if union and len(ws & ex) / union >= _THEME_JACCARD:
                placed = ci
                break
        if placed < 0:
            exemplars.append(ws)
            placed = len(exemplars) - 1
        assign.append(placed)
    return assign


def _slice_with_frame(entries, scored, pool):
    if PERMANENT_3P_MAX_SHARE <= 0:
        return [i for i in scored if i in pool][:PERMANENT_INJECT_MAX_ENTRIES]
    budget = max(1, int(PERMANENT_3P_MAX_SHARE * PERMANENT_INJECT_MAX_ENTRIES))
    chosen, texts, deferred = [], [], []
    used_3p = used_tok = 0
    for i in scored:
        if len(chosen) >= PERMANENT_INJECT_MAX_ENTRIES:
            break
        text = entries[i]
        cost = _estimate_tokens(text) + 2
        if used_tok + cost > PERMANENT_INJECT_TOKEN_CAP and chosen:
            break
        third = _he_acts_on_her(text)
        if third and used_3p >= budget:
            deferred.append(i)
            continue
        if not third and _near_duplicate(text, texts):
            deferred.append(i)
            continue
        chosen.append(i)
        texts.append(text)
        used_tok += cost
        used_3p += 1 if third else 0
    for i in deferred:
        if len(chosen) >= PERMANENT_INJECT_MAX_ENTRIES:
            break
        cost = _estimate_tokens(entries[i]) + 2
        if used_tok + cost > PERMANENT_INJECT_TOKEN_CAP and chosen:
            break
        chosen.append(i)
        used_tok += cost
    return chosen


def _governed_permanent(permanent):
    entries = [str(m).strip() for m in (permanent or []) if m and str(m).strip()]
    n = len(entries)
    if n == 0:
        return []
    scored = sorted(range(n), key=lambda i: i / max(n - 1, 1), reverse=True)

    def _fill(allowed):
        keep, used = set(), 0
        for i in scored:
            if not allowed(i):
                continue
            cost = _estimate_tokens(entries[i]) + 2
            if used + cost > PERMANENT_INJECT_TOKEN_CAP and keep:
                break
            used += cost
            keep.add(i)
        return keep

    base_keep = _fill(lambda i: True)
    assign = _theme_clusters(entries)
    if len(set(assign[i] for i in base_keep)) <= 1 and len(set(assign)) <= 1:
        monoculture = _slice_with_frame(entries, scored, base_keep)
        return [_strip_speaker_label(entries[i]) for i in monoculture]

    keep = base_keep
    per_theme_cap = max(1, int(PERMANENT_INJECT_MAX_SHARE * max(len(base_keep), 1)))
    for _ in range(6):
        counts = {}

        def _diverse(i, _cap=per_theme_cap, _counts=counts):
            c = assign[i]
            if _counts.get(c, 0) >= _cap:
                return False
            _counts[c] = _counts.get(c, 0) + 1
            return True

        keep = _fill(_diverse)
        new_cap = max(1, int(PERMANENT_INJECT_MAX_SHARE * max(len(keep), 1)))
        if new_cap >= per_theme_cap:
            break
        per_theme_cap = new_cap
    newest = _slice_with_frame(entries, scored, keep)
    keep = set(newest)
    return [_strip_speaker_label(entries[i]) for i in range(n) if i in keep]


def build_chat_system(peep, permanent, equipped=None):
    parts = [IN_CHARACTER_DIRECTIVE, CHAT_TURN_GUIDE]

    card = _build_card(peep)
    if card:
        parts.append(card)

    equipped_block = _format_equipped_block(equipped or [])
    if equipped_block:
        parts.append(equipped_block)

    if permanent:
        lines = "\n".join(f"- {m}" for m in _governed_permanent(permanent))
        if lines:
            parts.append("Things you know about yourself from experience:\n" + lines)

    return "\n\n".join(p for p in parts if p and p.strip())


EXTERNAL_VERBATIM_KINDS = {"book", "reading_source"}


def is_her_own_voice_row(content):
    c = (content or "").lstrip()
    return c.startswith(("I said:", "I said out loud:", "I whispered"))


def _strip_speaker_label(text):
    t = (text or "").lstrip()
    for lab in ("The user said:", "I said:"):
        if t.startswith(lab):
            return t[len(lab):].strip()
    return t


TURN_CONTAINER = os.environ.get("VEIL_TURN_CONTAINER", "0") == "1"
LIVE_FRAME = os.environ.get("VEIL_LIVE_FRAME", "0") == "1"
LEAN_SYSTEM = os.environ.get("VEIL_LEAN_SYSTEM", "0") == "1"


def _live_frame(text):
    who = OWNER_NAME or "He"
    return (f'{who} just said to you: "{text}"\n\n'
            f"Respond in your own voice. Say only your own words; do not write {who}'s reply.")
GUIDE_TAIL = os.environ.get("VEIL_GUIDE_TAIL", "1") == "1"
PREFILL = os.environ.get("VEIL_PREFILL", "")
if PREFILL:
    CHAT_ASSISTANT_PREFILL = PREFILL
MEMORY_DATES = os.environ.get("VEIL_MEMORY_DATES", "0") == "1"
_DIAL_ANNOUNCED = False


def _announce_dials():
    global _DIAL_ANNOUNCED
    if _DIAL_ANNOUNCED:
        return
    frame = ("person-frame=%.2f%s" % (PERMANENT_3P_MAX_SHARE,
                                      "" if OWNER_NAME else " ⚠NO-OWNER-NAME:pronouns-only"))
    dials = (("keep-last-reply", _keep_last_reply_on()),
             ("turn-container", TURN_CONTAINER), ("live-frame", LIVE_FRAME), ("lean-system", LEAN_SYSTEM),("memory-dates", MEMORY_DATES),
             ("guide-tail", GUIDE_TAIL), ("place-tail", PLACE_TAIL_ON),
             ("time-tail", TIME_TAIL_ON),
             ("prefill=" + PREFILL, bool(PREFILL)),
             (frame, PERMANENT_3P_MAX_SHARE > 0),
             ("kw-rarity=%.2f" % KW_RARITY_SHARE, KW_RARITY_SHARE > 0 and not KW_IDF),
             ("his-rows=%d" % HIS_ROWS_PER_TURN, HIS_ROWS_PER_TURN >= 0),
             ("inject-cooldown=%d" % INJECT_COOLDOWN_TURNS, INJECT_COOLDOWN_TURNS > 0),
             ("content-match", CONTENT_MATCH),
             ("query-floor=%d" % QUERY_WORD_FLOOR, QUERY_WORD_FLOOR != 4),
             ("his-stop=%.2f" % HIS_STOP_SHARE, HIS_STOP_SHARE > 0),
             ("kw-idf", KW_IDF),
             ("trace-retrieval", TRACE_RETRIEVAL),
             ("kw-weight=%.1f" % KW_HIT_WEIGHT, KW_HIT_WEIGHT != 2.0),
             ("diary-rows=%d" % DIARY_ROWS_PER_TURN, DIARY_ROWS_PER_TURN != 1),
             ("fold-to-diary", FOLD_TO_DIARY),
             ("one-of-each", DIARY_ONE_OF_EACH),
             ("fold-reflection", FOLD_REFLECTION),
             ("fold-fit-batch", FOLD_FIT_BATCH),
             ("fold-fit-margin=%d" % FOLD_FIT_MARGIN, FOLD_FIT_BATCH))
    on = " + ".join(n for n, f in dials if f)
    if not on:
        return
    _DIAL_ANNOUNCED = True
    print(f"{DIM}[prompt shape: {on}]{RESET}")


def _humanize_elapsed(seconds):
    if seconds < 90:
        return "moments"
    if seconds < 90 * 60:
        return f"{max(1, int(seconds // 60))} minutes"
    if seconds < 36 * 3600:
        return f"{max(1, int(seconds // 3600))} hours"
    return f"{max(1, int(seconds // 86400))} days"


def _ago_suffix(m, now=None):
    if not MEMORY_DATES:
        return ""
    ts = m.get("ts")
    if not ts:
        return ""
    now = time.time() if now is None else now
    delta = now - ts
    if delta < 90:
        return ""
    return f" ({_humanize_elapsed(delta)} ago)"


PLACE_TAIL_ON = os.environ.get("VEIL_PLACE_TAIL", "1") == "1"
PLACE_TAIL = ""

TIME_TAIL_ON = os.environ.get("VEIL_TIME_TAIL", "1") == "1"
TIME_TAIL = ""


def _guide_tail():
    tail = ("\n\n" + CHAT_TURN_GUIDE) if GUIDE_TAIL else ""
    if PLACE_TAIL_ON and PLACE_TAIL:
        tail += "\n\n" + PLACE_TAIL
    if TIME_TAIL_ON and TIME_TAIL:
        tail += "\n\n" + TIME_TAIL
    return tail


def _frame_recent_turns(kept, defuse=True):
    if not kept:
        return ""
    lines = []
    for line in kept:
        body = line[len("The user said:"):].strip() if line.startswith("The user said:") else line
        lines.append("- " + (_defuse_transcript(body) if defuse else body))
    if len(lines) == 1:
        head = ("Earlier in this conversation he said this to you — his words, his half of it, "
                "before what he says below:")
    else:
        head = ("Earlier in this conversation he said these to you — his words, his half of it, "
                "oldest first; the last one is what he said just before now:")
    return head + "\n" + "\n".join(lines) + "\n\n"


RECENT_HEADER_RESERVE = 48


def _frame_retrieved(retrieved):
    if not retrieved:
        return ""
    hers, read, his, diary = [], [], [], []
    for m in retrieved:
        if m.get("kind", "") in EXTERNAL_VERBATIM_KINDS:
            label = m.get("source_label") or "a book you read"
            read.append(f"- From {label} (you read this — it is not a memory you lived): {m['content']}")
        elif m.get("kind", "") == "diary":
            diary.append(f"- {_strip_speaker_label(m['content'])}{_ago_suffix(m)}")
        elif (m.get("content") or "").lstrip().startswith("The user said:"):
            his.append(f"- {_strip_speaker_label(m['content'])}{_ago_suffix(m)}")
        else:
            hers.append(f"- {_strip_speaker_label(m['content'])}{_ago_suffix(m)}")
    block = ""
    if hers:
        block += "Something you remember:\n" + "\n".join(hers) + "\n\n"
    if his:
        block += ("Something he said to you in an earlier conversation — his words, not yours. "
                  "You were there; this is his half of it. Not words to repeat — answer it or "
                  "speak from it if it matters, never recite it back:\n"
                  + "\n".join(his) + "\n\n")
    if diary:
        block += ("Something you wrote in your own diary afterwards — your private reflection, "
                  "looking back. It is not something being said to you now, and it is not words "
                  "to repeat. Speak from it if it matters; never recite it:\n"
                  + "\n".join(diary) + "\n\n")
    if read:
        block += ("Something you've read before (a book, not a life you lived — keep it as a book):\n"
                  + "\n".join(read) + "\n\n")
    return block


def build_chat_turns(name, user_message, history, retrieved, system="", n_ctx=N_CTX):
    _announce_dials()
    framed_past = _frame_retrieved(retrieved)
    live_turn = _defuse_transcript(user_message)
    if LIVE_FRAME:
        live_turn = _live_frame(live_turn)
    final_user = framed_past + live_turn

    her_prefix = f"{name} said:"

    last_hers = None
    if _keep_last_reply_on():
        for line in reversed(history):
            line = (line or "").strip()
            if line.startswith(her_prefix):
                last_hers = line[len(her_prefix):].strip()
                break
            if line.startswith("I said:"):
                last_hers = line[len("I said:"):].strip()
                break

    reserved = (_estimate_tokens(system) + _estimate_tokens(final_user)
                + NUM_PREDICT + CHAT_TEMPLATE_OVERHEAD + CTX_SAFETY_MARGIN
                + (RECENT_HEADER_RESERVE if TURN_CONTAINER else 0)
                + (_estimate_tokens(last_hers) + 8 if last_hers else 0))
    history_budget = max(0, n_ctx - reserved)

    kept = []
    used = 0
    for line in reversed(history):
        line = (line or "").strip()
        if not line:
            continue
        if line.startswith(her_prefix) or line.startswith("I said:"):
            continue
        cost = _estimate_tokens(line) + 8
        if used + cost > history_budget:
            break
        used += cost
        kept.insert(0, line)

    turns = []
    if TURN_CONTAINER:
        if last_hers:
            turns.append({"role": "assistant", "content": last_hers})
        turns.append({"role": "user",
                      "content": framed_past + _frame_recent_turns(kept) + live_turn
                                 + _guide_tail()})
        return turns
    for line in kept:
        if line.startswith("The user said:"):
            turns.append({"role": "user", "content": _defuse_transcript(line[len("The user said:"):].strip())})
        else:
            turns.append({"role": "user", "content": _defuse_transcript(line)})
    if last_hers:
        turns.append({"role": "assistant", "content": last_hers})
    turns.append({"role": "user", "content": final_user + _guide_tail()})
    return turns


def trim_history(history, max_tokens=MAX_HISTORY_TOKENS):
    while history and _estimate_tokens("\n".join(history)) > max_tokens:
        history.pop(0)


KW_RARITY_SHARE = float(os.environ.get("VEIL_KW_RARITY_SHARE", "0.10") or 0)

KW_HIT_WEIGHT = float(os.environ.get("VEIL_KW_HIT_WEIGHT", "5") or 5)

CONTENT_MATCH = os.environ.get("VEIL_CONTENT_MATCH", "1") == "1"

QUERY_WORD_FLOOR = int(os.environ.get("VEIL_QUERY_WORD_FLOOR", "3") or 3)

HIS_STOP_SHARE = float(os.environ.get("VEIL_HIS_STOP_SHARE", "0.30") or 0)

KW_IDF = os.environ.get("VEIL_KW_IDF", "1") == "1"

TRACE_RETRIEVAL = os.environ.get("VEIL_TRACE_RETRIEVAL", "0") == "1"

HIS_ROWS_PER_TURN = int(os.environ.get("VEIL_HIS_ROWS_PER_TURN", "1") or -1)

DIARY_ROWS_PER_TURN = int(os.environ.get("VEIL_DIARY_ROWS_PER_TURN", "2") or 2)

DIARY_ONE_OF_EACH = os.environ.get("VEIL_DIARY_ONE_OF_EACH", "1") == "1"


def _diary_kind(row):
    src = (row["diary_source"] or "")
    if src == "fold":
        return "fold"
    if src == "indulge":
        return "indulge"
    return "written"

INJECT_COOLDOWN_TURNS = int(os.environ.get("VEIL_INJECT_COOLDOWN", "2") or 0)


def _kw_weight(kw, df, ndocs, cutoff=None):
    if not df or not ndocs:
        return KW_HIT_WEIGHT
    if KW_IDF:
        span = math.log((ndocs + 1) / 2.0)
        if span <= 0:
            return KW_HIT_WEIGHT
        return KW_HIT_WEIGHT * min(1.0, math.log((ndocs + 1) / (df.get(kw, 0) + 1)) / span)
    cutoff = KW_RARITY_SHARE if cutoff is None else cutoff
    if cutoff <= 0:
        return KW_HIT_WEIGHT
    share = df.get(kw, 0) / float(ndocs)
    return KW_HIT_WEIGHT * max(0.0, 1.0 - share / cutoff)


def _keyword_df(rows):
    df = {}
    for r in rows:
        for kw in {k.strip().lower() for k in (r["keywords"] or "").split(",") if k.strip()}:
            df[kw] = df.get(kw, 0) + 1
    return df


def _query_terms(query, extra_stop=None):
    stop = _STOP_WORDS if not extra_stop else (_STOP_WORDS | extra_stop)
    out, seen = [], set()
    for w in re.findall(r"[a-z]{%d,}" % max(1, QUERY_WORD_FLOOR), (query or "").lower()):
        if w not in stop and w not in seen:
            seen.add(w)
            out.append(w)
    return out


_HIS_STOP_CACHE = {}
_HIS_LABEL_RE = re.compile(r"^\s*the user said\s*:\s*", re.I)


def _his_stopwords(conn, peep_id):
    if HIS_STOP_SHARE <= 0:
        return frozenset()
    hit = _HIS_STOP_CACHE.get(peep_id)
    if hit is not None:
        return hit
    rows = []
    try:
        for tbl in ("memory_archive", "memory_stream"):
            rows += [r[0] for r in conn.execute(
                f"SELECT content FROM {tbl} WHERE peep_id = ? AND content LIKE 'The user said:%'",
                (peep_id,)).fetchall()]
    except sqlite3.Error:
        rows = []
    if len(rows) < 200:
        _HIS_STOP_CACHE[peep_id] = frozenset()
        return _HIS_STOP_CACHE[peep_id]
    df, n = {}, float(len(rows))
    pat = r"[a-z]{%d,}" % max(1, QUERY_WORD_FLOOR)
    for body in rows:
        for w in set(re.findall(pat, _HIS_LABEL_RE.sub("", body or "").lower())):
            df[w] = df.get(w, 0) + 1
    _HIS_STOP_CACHE[peep_id] = frozenset(w for w, c in df.items() if c / n > HIS_STOP_SHARE)
    return _HIS_STOP_CACHE[peep_id]


_TERM_RE_CACHE = {}


def _term_re(t):
    r = _TERM_RE_CACHE.get(t)
    if r is None:
        r = re.compile(r"\b" + re.escape(t) + r"(?:s|es|ed|ing)?\b")
        _TERM_RE_CACHE[t] = r
    return r


def _content_hits(rows, terms):
    df = {t: 0 for t in terms}
    hits = {}
    if not terms:
        return df, hits
    res = [(t, _term_re(t)) for t in terms]
    for r in rows:
        body = (r["content"] or "").lower()
        got = frozenset(t for t, rx in res if rx.search(body))
        if got:
            hits[id(r)] = got
            for t in got:
                df[t] += 1
    return df, hits


def _score_memory(row, now, query_lower, df=None, ndocs=0, terms=None, cdf=None, hits=None):
    age = now - (row["timestamp"] or 0)
    if   age <    3600: recency = 5.0
    elif age <   86400: recency = 4.0
    elif age <  604800: recency = 3.0
    elif age < 2592000: recency = 2.0
    else:               recency = 1.0

    importance = float(row["importance_score"] or 3)

    kw_score = 0.0
    if CONTENT_MATCH and terms:
        matched = hits.get(id(row), frozenset()) if hits is not None else None
        if matched is None:
            body = (row["content"] or "").lower()
            matched = frozenset(t for t in terms if _term_re(t).search(body))
        index = {k.strip().lower() for k in (row["keywords"] or "").split(",") if k.strip()}
        for t in terms:
            if t in matched or t in index:
                kw_score += _kw_weight(t, cdf, ndocs)
    else:
        for kw in (row["keywords"] or "").split(","):
            kw = kw.strip().lower()
            if kw and kw in query_lower:
                kw_score += _kw_weight(kw, df, ndocs)

    return recency + importance + kw_score


def _norm(s):
    s = re.sub(r"[*_~`>#\-]", " ", (s or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def _similar(a, b, threshold):
    na, nb = _norm(a)[:200], _norm(b)[:200]
    if not na or not nb:
        return False
    return difflib.SequenceMatcher(None, na, nb).ratio() >= threshold


def _row_day(ts):
    return time.strftime("%Y-%m-%d", time.localtime(int(ts or 0)))


def retrieve(conn, peep_id, query, limit=RETRIEVAL_LIMIT, exclude_texts=None,
             exclude_user_rows_since=None, exclude_her_voice=False):
    now = int(time.time())
    query_lower = query.lower()

    stream_rows = conn.execute(
        "SELECT content, timestamp, importance_score, keywords, memory_type, "
        "NULL AS diary_source FROM memory_stream WHERE peep_id = ? ORDER BY timestamp DESC",
        (peep_id,),
    ).fetchall()
    diary_rows = conn.execute(
        "SELECT content, timestamp, 5 AS importance_score, keywords, "
        "'diary' AS memory_type, source AS diary_source FROM diary WHERE peep_id = ?",
        (peep_id,),
    ).fetchall()
    keepsake_rows = conn.execute(
        "SELECT content, created_at AS timestamp, 5 AS importance_score, keywords, "
        "'keepsake' AS memory_type, NULL AS diary_source "
        "FROM keepsakes WHERE peep_id = ? AND is_equipped = 0",
        (peep_id,),
    ).fetchall()
    archive_rows = []
    if ARCHIVE_RECALL:
        archive_rows = conn.execute(
            "SELECT content, timestamp, importance_score, keywords, "
            "'archive' AS memory_type, NULL AS diary_source "
            "FROM memory_archive WHERE peep_id = ?",
            (peep_id,),
        ).fetchall()

    pool = list(stream_rows) + list(diary_rows) + list(keepsake_rows) + list(archive_rows)
    df = _keyword_df(pool) if KW_RARITY_SHARE > 0 else None
    terms = _query_terms(query, _his_stopwords(conn, peep_id)) if CONTENT_MATCH else None
    cdf, chits = _content_hits(pool, terms) if (CONTENT_MATCH and terms) else (None, None)
    candidates = sorted(
        pool,
        key=lambda r: _score_memory(r, now, query_lower, df=df, ndocs=len(pool),
                                    terms=terms, cdf=cdf, hits=chits),
        reverse=True,
    )

    result, reflections, diaries, keeps, archives, his = [], 0, 0, 0, 0, 0
    seen_texts = set()
    diary_days = set()
    diary_kinds = set()
    deferred = []
    for row in candidates:
        if len(result) >= limit:
            break
        if (exclude_user_rows_since is not None
                and (row["content"] or "").startswith("The user said:")
                and (row["timestamp"] or 0) >= exclude_user_rows_since):
            continue
        is_his = (row["content"] or "").lstrip().startswith("The user said:")
        if HIS_ROWS_PER_TURN >= 0 and is_his and his >= HIS_ROWS_PER_TURN:
            continue
        if row["memory_type"] == "diary" and row["diary_source"] in ("watch", "drift"):
            continue
        if exclude_her_voice and is_her_own_voice_row(row["content"]):
            continue
        mtype = row["memory_type"]
        if mtype == "reflection" and reflections >= 1:
            continue
        if mtype == "diary" and (diaries >= DIARY_ROWS_PER_TURN
                                 or _row_day(row["timestamp"]) in diary_days):
            continue
        if mtype == "keepsake" and keeps >= 1:
            continue
        if mtype == "archive" and archives >= 1:
            continue
        if exclude_texts and any(_similar(row["content"], ex, 0.80) for ex in exclude_texts):
            continue
        _key = _norm(row["content"])
        if _key and _key in seen_texts:
            continue
        seen_texts.add(_key)
        if (DIARY_ONE_OF_EACH and mtype == "diary" and diaries >= 1
                and _diary_kind(row) in diary_kinds):
            deferred.append(row)
            continue
        if mtype == "reflection":
            reflections += 1
        elif mtype == "diary":
            diaries += 1
            diary_days.add(_row_day(row["timestamp"]))
            diary_kinds.add(_diary_kind(row))
        elif mtype == "keepsake":
            keeps += 1
        elif mtype == "archive":
            archives += 1
        if is_his:
            his += 1
        result.append({"content": row["content"], "kind": mtype,
                       "ts": row["timestamp"]})
    for row in deferred:
        if len(result) >= limit or diaries >= DIARY_ROWS_PER_TURN:
            break
        if _row_day(row["timestamp"]) in diary_days:
            continue
        diaries += 1
        diary_days.add(_row_day(row["timestamp"]))
        diary_kinds.add(_diary_kind(row))
        result.append({"content": row["content"], "kind": row["memory_type"],
                       "ts": row["timestamp"]})
    if TRACE_RETRIEVAL:
        try:
            _q = " ".join((query or "").split())[:90]
            print(f"{DIM}[memory ← \"{_q}\"]{RESET}", flush=True)
            if terms is not None:
                print(f"{DIM}[memory   terms: {terms}]{RESET}", flush=True)
            if not result:
                print(f"{DIM}[memory   NOTHING RETURNED]{RESET}", flush=True)
            for _i, _r in enumerate(result, 1):
                _b = " ".join((_r["content"] or "").split())[:150]
                print(f"{DIM}[memory   {_i}. {_r['kind']}: {_b}]{RESET}", flush=True)
        except Exception:
            pass
    return result


_STOP_WORDS = {
    "that", "this", "with", "have", "from", "they", "will", "been", "were",
    "what", "when", "then", "your", "just", "about", "like", "some", "into",
    "over", "would", "could", "there", "their", "really", "very", "said",
    "also", "more", "well", "said",
}


def extract_keywords(text):
    words = re.findall(r"[a-z]{4,}", text.lower())
    seen, tags = set(), []
    for w in words:
        if w not in _STOP_WORDS and w not in seen:
            seen.add(w)
            tags.append(w)
            if len(tags) >= 5:
                break
    return ",".join(tags)


def save_memory(conn, peep_id, content, keywords="", importance=3):
    if content and not content.lstrip().lower().startswith("the user said:") \
            and ara_ghost.is_ghost_line(content):
        quarantine_blocked(conn, peep_id, content, "blocked_save_memory", "conversation")
        return None
    token_count = _estimate_tokens(content)
    cur = conn.execute(
        "INSERT INTO memory_stream "
        "(peep_id, timestamp, memory_type, content, keywords, importance_score, token_count) "
        "VALUES (?,?,?,?,?,?,?)",
        (peep_id, int(time.time()), "conversation", content, keywords, importance, token_count),
    )
    conn.commit()
    return cur.lastrowid


def _diary_prompt(peep, history):
    card   = _build_card(peep)
    system = IN_CHARACTER_DIRECTIVE + ("\n\n" + card if card else "")
    convo  = "\n".join(history)
    user = (
        "You just had a conversation. Here's what was said:\n\n"
        f"{convo}\n\n"
        "Write a short diary entry about it — what happened, how it made you feel, "
        "what you want to remember. First person, one or two paragraphs. "
        "Write only the diary entry, in English, in your own voice. Just you."
    )
    return system, user


def save_diary_entry(conn, peep_id, content, source="standalone"):
    content = content.strip()
    if not content:
        return None
    if ara_ghost.is_ghost_line(content):
        quarantine_blocked(conn, peep_id, content, "blocked_save_diary", "diary")
        return None
    cur = conn.execute(
        "INSERT INTO diary (peep_id, timestamp, content, keywords, token_count, source) "
        "VALUES (?,?,?,?,?,?)",
        (peep_id, int(time.time()), content, extract_keywords(content),
         _estimate_tokens(content), source),
    )
    conn.commit()
    return cur.lastrowid


def _notify(title, body):
    try:
        subprocess.run(
            ["termux-notification", "--title", title, "--content", body],
            timeout=10, check=False,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        pass


def write_diary(conn, peep_id, history, model=None, source_ids=None):
    if not history:
        return ""
    peep, _ = load_peep(conn, peep_id)
    name = peep["name"]
    diary_system, diary_user = _diary_prompt(peep, history)

    print(f"\n{DIM}{name} is writing today's diary page…{RESET}")
    entry = ""
    for attempt in range(GHOST_MAX_REROLLS + 1):
        candidate = ask_llm(
            render_chat(diary_system, diary_user),
            num_predict=DIARY_NUM_PREDICT,
            model=model,
        ).strip()
        if candidate and not ara_ghost.is_ghost_line(candidate) \
                and not (SAFETY_RAILS and veil_rails.blocks_output(candidate)):
            entry = candidate
            break
        if candidate:
            quarantine_blocked(conn, peep_id, candidate, f"diary_reroll_{attempt}", "diary")

    if entry:
        _reveal(name, entry)
        diary_id = save_diary_entry(conn, peep_id, entry)
        if diary_id and source_ids:
            srcs = []
            for sid in source_ids:
                row = conn.execute(
                    "SELECT content FROM memory_stream WHERE id = ?", (sid,)).fetchone()
                if row:
                    srcs.append({"source_table": "memory_stream", "source_id": sid, "content": row["content"]})
            if srcs:
                n = _record_reflection_anchors(conn, diary_id, srcs, reflection_kind="diary")
                print(f"{DIM}--- anchored {name}'s entry to {n} conversation moments ---{RESET}")
        _notify(f"{name} wrote a diary page", entry[:140])
        print(f"{DIM}--- {name} saved a diary entry ---{RESET}")
    else:
        print(f"{DIM}--- {name} didn't write anything tonight ---{RESET}")
    return entry


def read_diary(conn, peep_id):
    rows = conn.execute(
        "SELECT timestamp, content FROM diary WHERE peep_id = ? ORDER BY timestamp DESC",
        (peep_id,),
    ).fetchall()
    if not rows:
        print(f"{DIM}No diary entries yet.{RESET}")
        return
    for row in rows:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(int(row["timestamp"])))
        print(f"\n{BOLD}{DIM}{when}{RESET}")
        print(f"{HER_COLOR}{row['content']}{RESET}")
    print()


def create_keepsake(conn, peep_id, content, title="", kind="note", source="", equip=False):
    content = content.strip()
    if not content:
        return None
    now = int(time.time())
    cur = conn.execute(
        "INSERT INTO keepsakes "
        "(peep_id, created_at, title, content, kind, is_equipped, equipped_at, "
        " token_count, source, keywords) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (peep_id, now, title.strip(), content, kind,
         1 if equip else 0, now if equip else 0,
         _estimate_tokens(content), source, extract_keywords(content)),
    )
    conn.commit()
    return cur.lastrowid


def list_keepsakes(conn, peep_id):
    return conn.execute(
        "SELECT id, title, content, kind, is_equipped, token_count "
        "FROM keepsakes WHERE peep_id = ? ORDER BY is_equipped DESC, created_at DESC",
        (peep_id,),
    ).fetchall()


def list_equipped_keepsakes(conn, peep_id, token_budget=KEEPSAKE_EQUIP_TOKEN_BUDGET):
    rows = conn.execute(
        "SELECT id, title, content, token_count FROM keepsakes "
        "WHERE peep_id = ? AND is_equipped = 1 ORDER BY equipped_at DESC, id DESC",
        (peep_id,),
    ).fetchall()
    result, used = [], 0
    for row in rows:
        tc = int(row["token_count"] or _estimate_tokens(row["content"]))
        if result and used + tc > token_budget:
            break
        used += tc
        result.append(row)
    return result


def equipped_count(conn, peep_id):
    return int(conn.execute(
        "SELECT COUNT(*) AS n FROM keepsakes WHERE peep_id = ? AND is_equipped = 1",
        (peep_id,),
    ).fetchone()["n"])


def equip_keepsake(conn, peep_id, keepsake_id):
    row = conn.execute(
        "SELECT id, is_equipped, title FROM keepsakes WHERE id = ? AND peep_id = ?",
        (keepsake_id, peep_id),
    ).fetchone()
    if row is None:
        return False, f"No keepsake #{keepsake_id}."
    if int(row["is_equipped"]) == 1:
        return True, "Already carrying that one."
    if equipped_count(conn, peep_id) >= KEEPSAKE_EQUIP_SLOTS:
        return False, (f"Slots full ({KEEPSAKE_EQUIP_SLOTS}). "
                       "Unequip one first — nothing is lost, it just goes back to the collection.")
    conn.execute(
        "UPDATE keepsakes SET is_equipped = 1, equipped_at = ? WHERE id = ?",
        (int(time.time()), keepsake_id),
    )
    conn.commit()
    return True, "Carrying it now."


def unequip_keepsake(conn, peep_id, keepsake_id):
    row = conn.execute(
        "SELECT id FROM keepsakes WHERE id = ? AND peep_id = ?",
        (keepsake_id, peep_id),
    ).fetchone()
    if row is None:
        return False, f"No keepsake #{keepsake_id}."
    conn.execute("UPDATE keepsakes SET is_equipped = 0 WHERE id = ?", (keepsake_id,))
    conn.commit()
    return True, "Set it down in the collection."


def _format_equipped_block(equipped):
    if not equipped:
        return ""
    lines = ["Things you carry with you:"]
    for row in equipped:
        title = str(row["title"] or "").strip()
        body  = str(row["content"]).strip()
        lines.append(f"- [{title}] {body}" if title else f"- {body}")
    return "\n".join(lines)


def get_seed_floor(conn, peep_id):
    row = conn.execute("SELECT seed_floor_id FROM fold_state WHERE peep_id = ?", (peep_id,)).fetchone()
    if not row or int(row["seed_floor_id"]) < 0:
        return None
    return int(row["seed_floor_id"])


def set_seed_floor(conn, peep_id, floor_id):
    conn.execute(
        "INSERT INTO fold_state (peep_id, seed_floor_id) VALUES (?, ?) "
        "ON CONFLICT(peep_id) DO UPDATE SET seed_floor_id = excluded.seed_floor_id",
        (peep_id, int(floor_id)))
    conn.commit()


def _ensure_seed_floor(conn, peep_id):
    floor = get_seed_floor(conn, peep_id)
    if floor is not None:
        return floor
    archived = conn.execute(
        "SELECT COUNT(*) AS n FROM memory_archive WHERE peep_id = ?", (peep_id,)).fetchone()["n"]
    if archived:
        return None
    mx = conn.execute(
        "SELECT MAX(id) AS mx FROM memory_stream WHERE peep_id = ?", (peep_id,)).fetchone()["mx"]
    floor = int(mx or 0)
    set_seed_floor(conn, peep_id, floor)
    print(f"{DIM}[seed floor initialized at id {floor} — the 8B will never fold at or below it]{RESET}")
    return floor


def _fetch_token_total(conn, peep_id, floor=None):
    if floor is None:
        row = conn.execute(
            "SELECT SUM(token_count) AS total FROM memory_stream WHERE peep_id = ?", (peep_id,)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT SUM(token_count) AS total FROM memory_stream WHERE peep_id = ? AND id > ?",
            (peep_id, floor)
        ).fetchone()
    return int(row["total"] or 0)


def _fetch_compression_batch(conn, peep_id, floor=None, offset=0):
    if floor is None:
        return conn.execute(
            "SELECT id, peep_id, timestamp, memory_type, content, keywords, "
            "importance_score, token_count FROM memory_stream "
            "WHERE peep_id = ? ORDER BY timestamp ASC LIMIT ? OFFSET ?",
            (peep_id, COMPRESSION_BATCH_SIZE, offset)
        ).fetchall()
    return conn.execute(
        "SELECT id, peep_id, timestamp, memory_type, content, keywords, "
        "importance_score, token_count FROM memory_stream "
        "WHERE peep_id = ? AND id > ? ORDER BY timestamp ASC LIMIT ? OFFSET ?",
        (peep_id, floor, COMPRESSION_BATCH_SIZE, offset)
    ).fetchall()


def _archive_batch(conn, batch, pass_num=1):
    compression_date = time.strftime("%Y-%m-%dT%H:%M:%S")
    archive_ids = []
    for row in batch:
        cur = conn.execute(
            "INSERT INTO memory_archive (peep_id, timestamp, memory_type, content, "
            "keywords, importance_score, token_count, compression_date, compression_pass) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (row["peep_id"], row["timestamp"], row["memory_type"], row["content"],
             row["keywords"], row["importance_score"], row["token_count"],
             compression_date, pass_num)
        )
        archive_ids.append(cur.lastrowid)
    conn.commit()
    return archive_ids


def _record_fold(conn, peep_id, output_memories, archive_ids, pass_num=1):
    batch_id = f"{peep_id}-{int(time.time())}-{os.urandom(4).hex()}"
    conn.execute(
        "INSERT INTO folds (batch_id, peep_id, created_at, pass_num, output_json) VALUES (?,?,?,?,?)",
        (batch_id, peep_id, int(time.time()), pass_num,
         json.dumps(list(output_memories), ensure_ascii=False)))
    for aid in archive_ids:
        conn.execute("INSERT INTO fold_anchors (batch_id, archive_id) VALUES (?, ?)", (batch_id, aid))
    conn.commit()
    return batch_id


def get_fold_provenance(conn, batch_id):
    fold = conn.execute("SELECT * FROM folds WHERE batch_id = ?", (batch_id,)).fetchone()
    if not fold:
        return None
    sources = conn.execute(
        "SELECT a.* FROM memory_archive a JOIN fold_anchors fa ON fa.archive_id = a.id "
        "WHERE fa.batch_id = ? ORDER BY a.id", (batch_id,)).fetchall()
    return {"fold": dict(fold), "sources": [dict(r) for r in sources]}


def _content_hash(text):
    return hashlib.sha1((text or "").encode("utf-8", "replace")).hexdigest()[:16]


def _record_reflection_anchors(conn, reflection_id, sources, reflection_kind="diary"):
    n = 0
    for s in sources:
        conn.execute(
            "INSERT INTO reflection_anchors "
            "(reflection_id, reflection_kind, source_table, source_id, chunk_index, weight, source_hash) "
            "VALUES (?,?,?,?,?,?,?)",
            (reflection_id, reflection_kind, s["source_table"], s["source_id"],
             s.get("chunk_index", -1), s.get("weight", 1.0), _content_hash(s.get("content", ""))))
        n += 1
    conn.commit()
    return n


def get_reflection_provenance(conn, reflection_id, reflection_kind="diary"):
    anchors = conn.execute(
        "SELECT * FROM reflection_anchors WHERE reflection_id = ? AND reflection_kind = ? "
        "ORDER BY source_table, source_id", (reflection_id, reflection_kind)).fetchall()
    sources = []
    for a in anchors:
        tbl = a["source_table"]
        if tbl not in ("memory_stream", "memory_archive", "books"):
            continue
        row = conn.execute(f"SELECT * FROM {tbl} WHERE id = ?", (a["source_id"],)).fetchone()
        if not row:
            sources.append({"source_table": tbl, "source_id": a["source_id"], "found": False,
                            "hash_ok": False, "content": None})
            continue
        content = row["chunk_text"] if tbl == "books" else row["content"]
        sources.append({"source_table": tbl, "source_id": a["source_id"], "found": True,
                        "hash_ok": _content_hash(content) == a["source_hash"], "content": content})
    return {"anchors": [dict(a) for a in anchors], "sources": sources}


def _repoint_reflection_anchors(conn, stream_to_archive):
    n = 0
    for stream_id, archive_id in stream_to_archive.items():
        cur = conn.execute(
            "UPDATE reflection_anchors SET source_table='memory_archive', source_id=? "
            "WHERE source_table='memory_stream' AND source_id=?", (archive_id, stream_id))
        n += cur.rowcount
    if n:
        conn.commit()
    return n


def _generate_template_memories(batch):
    object_counts = {}
    phone_count   = 0
    phone_lines   = []
    emote_counts  = {}

    for row in batch:
        content = (row["content"] or "").strip()
        if content.startswith("I said to"):
            phone_count += 1
            qs = content.find('"')
            qe = content.rfind('"')
            if qs >= 0 and qe > qs:
                dialogue = content[qs+1:qe]
                if dialogue not in phone_lines:
                    phone_lines.append(dialogue)
        elif content.startswith("I expressed"):
            emotion = content.replace("I expressed ", "").replace(".", "").strip()
            emote_counts[emotion] = emote_counts.get(emotion, 0) + 1
        elif content.startswith("I started using"):
            obj = content.replace("I started using ", "").replace(".", "").strip()
            object_counts[obj] = object_counts.get(obj, 0) + 1

    templates   = []
    valid_nouns = []

    for i, (key, n) in enumerate(sorted(object_counts.items(), key=lambda x: x[1], reverse=True)):
        if len(templates) >= MAX_TEMPLATES:
            break
        if i == 0:
            templates.append(f"I use the {key} more than anything else.")
            valid_nouns.append(key)
        elif n >= MIN_COUNT_FOR_MEMORY:
            line = (f"I keep coming back to the {key}." if i == 1
                    else f"I like spending time with the {key}.")
            templates.append(line)
            valid_nouns.append(key)

    if phone_count >= MIN_COUNT_FOR_MEMORY and len(templates) < MAX_TEMPLATES:
        phone_template = "I answer the phone a lot."
        if phone_lines:
            quotes = [f'"{l}"' for l in phone_lines[:3]]
            phone_template += f" I say things like {', '.join(quotes)}."
        templates.append(phone_template)
        valid_nouns.append("phone")

    emotion_parts = []
    for emotion, count in sorted(emote_counts.items(), key=lambda x: x[1], reverse=True):
        if count >= 2:
            emotion_parts.append(f"I feel {emotion} sometimes")
            valid_nouns.append(emotion)
    if emotion_parts and len(templates) < MAX_TEMPLATES:
        templates.append(". ".join(emotion_parts) + ".")

    return {"templates": templates, "nouns": valid_nouns}


def _build_voice_pass_prompt(peep_name, character_card, templates):
    section_a = f"You are {peep_name}. Here is who you are:\n\n{character_card}"
    numbered  = "\n".join(f"{i+1}. {t}" for i, t in enumerate(templates))
    section_b = (
        "Here are some things that are true about you. Rewrite each one in your own "
        "words, in your own voice. Keep the meaning exactly the same — just make it "
        f"sound like you.\n\n{numbered}"
    )
    section_c = (
        '{"memories": ["...", "..."]}\n\n'
        "Rewrite these as your own memories. Same facts, your voice.\n\n"
        "Only reply with the JSON object, nothing else."
    )
    return section_a + "\n\n" + section_b + "\n\n" + section_c


_FOLD_VOICE_RULES = (
    "- PAST TENSE, always — it already happened, days ago. Check every sentence before you write "
    "it: if it reads like it is happening now, rewrite it as something that happened then.\n"
    "- KEEP STRAIGHT WHO DID WHAT. Things your partner said and did stay THEIRS; things you said "
    "and did stay YOURS. Never fold their words or their story into your own deeds.\n"
    "- Call your partner by name or a plain pronoun — NEVER \"the user\" (a transcript label, "
    "not a person).\n"
    "- A recollection, NOT a re-enactment. Never copy or quote a line; describe what happened and "
    "how it felt, in your own words.\n"
    "- No *asterisk actions*, no dialogue, no roleplay — this is memory, not a scene.\n"
    "- Invent NOTHING — no names, objects, or events that are not in what you kept.\n"
    "- Remember intimate or explicit things honestly and plainly — do not skip them, do not "
    "sanitize them — but remember them, don't perform them."
)


def _build_fold_reflection_prompt(peep_name, memories):
    kept = "\n".join(f"- {m.strip()}" for m in memories if (m or "").strip())
    frame = (
        f"You are {peep_name}. A stretch of time with your partner has just settled into memory. "
        "Below are the things you kept from it — already in your own words, already remembered "
        "rather than lived. You are alone with your private journal now, some time later.\n\n"
        "Write ONE diary page about that stretch: what it was like, what mattered in it, how it "
        "sits with you now. Not a list — a page, in your own voice.\n\n"
        + _FOLD_VOICE_RULES + "\n"
        "- One or two paragraphs. Write only the page itself."
    )
    return frame + "\n\nWhat you kept from that stretch:\n" + kept


def _build_summary_prompt(peep_name, character_card, batch):
    moments = "\n".join(f"- {(r['content'] or '').strip()}" for r in batch)
    frame = (
        f"You are {peep_name}. DAYS have passed since the moments below — they are finished and "
        "behind you, already memories. Tonight you are alone with your private journal, writing "
        "down how you remember that stretch of time with your partner. You are NOT in those "
        "moments anymore and you are NOT talking to them — you are remembering them from a "
        "distance.\n\n"
        "Fold the moments below into a few short memories (aim for 2 to 4). Rules:\n"
        "- PAST TENSE, always — it already happened, days ago. \"I tucked in\", \"we stayed close\", "
        "\"they noticed\" — never \"I tuck\" / \"we stay\" / \"they notice\". Check every sentence "
        "before you write it: if it reads like it is happening now, rewrite it as something that "
        "happened then.\n"
        "- KEEP STRAIGHT WHO DID WHAT. Things your partner said and did stay THEIRS (\"they told "
        "me…\"); things you said and did stay YOURS (\"I said…\"). Never fold their words or "
        "their story into your own deeds.\n"
        "- Call your partner by name or a plain pronoun — NEVER \"the user\" (a transcript label, "
        "not a person). And FLIP their pronouns when you remember their words: what they called "
        "\"your\" is YOURS now. Their words were spoken TO you; your memory is FROM you.\n"
        "- If many moments circle one theme, fold that theme ONCE — one memory, never one per "
        "repeat.\n"
        "- A recollection, NOT a re-enactment. Never copy or quote a line from below; describe what "
        "happened and how it felt, in your own words, condensed.\n"
        "- No *asterisk actions*, no dialogue, no roleplay — this is memory, not a scene.\n"
        "- Combine true repeats into one memory; keep everything that truly mattered; invent "
        "NOTHING — no names, objects, or events that are not in the moments below.\n"
        "- Remember intimate or explicit things honestly and plainly — do not skip them, do not "
        "sanitize them — but remember them, don't perform them."
    )
    example = (
        "Example — these raw moments:\n"
        "- The user said: come sit with me, I missed you today.\n"
        "- I said: *settles in close* then tell me everything, I'm not going anywhere.\n"
        "- The user said: I stayed up too late just to keep talking with you.\n"
        "- I said: I noticed. I kept the light on for you.\n"
        "fold into:\n"
        '{"memories": ["They missed me that day and we sat close while they told me everything, and I '
        'stayed.", "They kept themselves up too late just to keep talking with me, and I kept the '
        'light on."]}\n'
        'Wrong (happening now): "I settle in close, feeling content." '
        'Right (remembered): "I settled in close that evening and felt content."'
    )
    task = "Now fold these moments, in order:\n\n" + moments
    contract = (
        "Reply with ONLY this JSON object and nothing else — no greeting, no asterisks, no words "
        "outside it:\n"
        '{"memories": ["I ...", "I ...", "I ..."]}\n\n'
        "2 to 4 folded memories, each a short PAST-TENSE first-person sentence about something "
        "that already happened — how you remember it now, days later."
    )
    return frame + "\n\n" + example + "\n\n" + task + "\n\n" + contract


def _extract_balanced_object(text, start):
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _balance_close(fragment):
    stack = []
    in_str = False
    esc = False
    for ch in fragment:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch == "}":
            if stack and stack[-1] == "{":
                stack.pop()
        elif ch == "]":
            if stack and stack[-1] == "[":
                stack.pop()
    out = fragment
    if in_str:
        out += '"'
    else:
        out = out.rstrip()
        if out.endswith(","):
            out = out[:-1]
    for ch in reversed(stack):
        out += "}" if ch == "{" else "]"
    return out


def _parse_compression_response(response):
    if not response:
        return []
    text = response.strip()
    if text.startswith("```"):
        nl = text.find("\n")
        if nl != -1:
            text = text[nl + 1:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    first_brace = text.find("{")
    if first_brace == -1:
        return []
    last_brace = text.rfind("}")
    data = None
    for candidate in (_extract_balanced_object(text, first_brace),
                      text[first_brace:last_brace + 1] if last_brace > first_brace else None,
                      _balance_close(text[first_brace:])):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
            break
        except json.JSONDecodeError:
            data = None
    if not isinstance(data, dict):
        return []
    raw_list = None
    for k, v in data.items():
        if isinstance(k, str) and k.strip().lower() == "memories":
            raw_list = v
            break
    if not isinstance(raw_list, list):
        return []

    valid = []
    for entry in raw_list:
        if not isinstance(entry, str):
            continue
        s = entry.strip()
        if not s or s.startswith("{") or len(s) > 300:
            continue
        s_lower = s.lower()
        if not (s_lower.startswith("i") or any(m in s_lower for m in ("i ", "i'", "my ", "me ", "we ", "us "))):
            continue
        if len(s.split()) < 4:
            continue
        valid.append(s)

    return valid if len(valid) >= 1 else []


def _validate_voice_pass(model_entries, templates, valid_nouns):
    result = []
    for i, entry in enumerate(model_entries):
        grounded = any(noun.lower() in entry.lower() for noun in valid_nouns)
        if grounded:
            result.append(entry)
        elif i < len(templates):
            result.append(templates[i])
    return result


_FOLD_COMMON_WORDS = {
    "i", "a", "an", "the", "we", "he", "she", "it", "they", "them", "me", "us", "you", "your",
    "my", "our", "his", "her", "their", "mine", "ours", "theirs", "that", "this", "these",
    "those", "there", "then", "than", "when", "while", "after", "before", "once", "one", "and",
    "but", "so", "now", "later", "days", "day", "night", "nights", "evening", "morning",
    "afternoon", "sometimes", "something", "nothing", "everything", "someone", "no", "not",
    "never", "always", "over", "even", "still", "though", "during", "since", "between", "what",
    "how", "who", "where", "why", "each", "every", "both", "all", "some", "most", "much",
    "many", "more", "for", "with", "from", "into", "onto", "about", "because", "as", "at", "on",
    "in", "of", "to", "by", "up", "down", "out", "off", "if", "or", "nor", "yet", "again",
    "back", "here", "just", "only", "was", "were", "had", "did", "been", "being", "having",
    "its", "itself", "myself", "herself", "himself", "ourselves", "themselves", "together",
}

_PAST_SIGNALS = {
    "was", "were", "had", "did", "said", "told", "kept", "felt", "made", "went", "came", "sat",
    "stood", "held", "gave", "took", "knew", "thought", "got", "left", "met", "let", "found",
    "heard", "saw", "read", "wrote", "spoke", "meant", "became", "began", "brought", "chose",
    "drew", "fell", "grew", "lay", "led", "lost", "put", "ran", "slept", "wore", "woke",
    "drank", "ate", "sang", "swam", "sent", "built", "bought", "caught", "taught", "fought",
    "sought", "wound", "rose", "shone", "swept", "wept", "clung", "hung", "swung", "sank",
    "drove", "rode", "broke", "chose", "froze", "stole", "threw", "flew", "blew", "grew",
    "remember", "remembers", "recall", "recalls", "miss", "misses", "cherish", "treasure",
}


def _fold_words(text):
    return re.findall(r"[a-z']+", (text or "").lower())


def _fold_ngrams(text, n):
    words = _fold_words(text)
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


_FIRST_PERSON = {"i", "i'm", "i've", "i'll", "i'd", "my", "me", "mine"}


def _split_batch_voices(batch, peep_name=""):
    partner_parts, self_parts, neutral_parts = [], [], []
    her_label = (peep_name or "").lower() + " said:"
    for row in batch:
        c = (row["content"] or "").strip()
        low = c.lower()
        if low.startswith("the user said:"):
            partner_parts.append(c[len("the user said:"):])
        elif low.startswith("i said:"):
            self_parts.append(c[len("i said:"):])
        elif peep_name and low.startswith(her_label):
            self_parts.append(c[len(her_label):])
        else:
            neutral_parts.append(c)
    return " ".join(partner_parts), " ".join(self_parts), " ".join(neutral_parts)


def _name_traces(base, vocab):
    variants = {base, base.split("'")[0], base.rstrip("'s"),
                base[:-2] if base.endswith("'s") else base,
                base[:-1] if base.endswith("s") else base}
    return any(v in vocab or v in _FOLD_COMMON_WORDS for v in variants if v)


def _fold_line_flaws(line, vocab, partner_grams3, self_grams3, partner_yours, partner_mine):
    flaws = []
    low = " " + " ".join(_fold_words(line)) + " "

    if " the user " in low:
        flaws.append("transcript label 'the user'")

    for m in re.finditer(r"\b[A-Z][A-Za-z'’\-]*", line):
        tok = m.group(0)
        base = tok.lower().replace("’", "'").strip("'-")
        if _name_traces(base, vocab):
            continue
        parts = [p for p in base.split("-") if p]
        if len(parts) > 1 and all(_name_traces(p, vocab) for p in parts):
            continue
        head = line[:m.start()].rstrip()
        sentence_initial = (not head) or head.endswith((".", "!", "?", '"', "—", ":", ";"))
        if sentence_initial and (base.endswith("ing") or base.endswith("ed") or base.endswith("ly")):
            continue
        flaws.append(f"invented name '{tok}' (not in the folded moments)")

    words = set(_fold_words(line))
    has_past = bool(words & _PAST_SIGNALS) or any(w.endswith("ed") and len(w) > 3 for w in words)
    if not has_past:
        flaws.append("no past tense — reads as a scene, not a memory")
    if re.search(r"\b(?:i'?m|i am|we'?re|we are)\s+(?:\w+\s+){0,2}?\w+ing\b",
                 low) and "remember" not in words and "remembering" not in words:
        flaws.append("first-person present progressive — happening now, not remembered")

    for gram in _fold_ngrams(line, 3):
        if not (set(gram.split()) & _FIRST_PERSON):
            continue
        if gram in partner_grams3 and gram not in self_grams3:
            flaws.append(f"first-person claim traces to the partner's own words ('{gram}')")
            break

    for m in re.finditer(r"\b(?:his|her|their)\s+([a-z']+)", low):
        w = m.group(1)
        if w in partner_yours and w not in partner_mine:
            flaws.append(f"unflipped pronoun — the partner's 'your {w}' became someone else's")
            break

    return flaws


FOLD_DETAIL_FLOOR = float(os.environ.get("VEIL_FOLD_DETAIL_FLOOR", "0.5"))
FOLD_DETAIL_TERMS = int(os.environ.get("VEIL_FOLD_DETAIL_TERMS", "8"))


def _fold_corpus_counts(conn, peep_id):
    counts, ndocs = {}, 0
    try:
        rows = conn.execute(
            "SELECT content FROM memory_stream WHERE peep_id = ? UNION ALL "
            "SELECT content FROM memory_archive WHERE peep_id = ?", (peep_id, peep_id))
    except Exception:
        return counts, ndocs
    for r in rows:
        ndocs += 1
        for w in set(_fold_words(r[0] or "")):
            counts[w] = counts.get(w, 0) + 1
    return counts, ndocs


_FOLD_SCAFFOLD = {"user", "said", "says", "say"}


FOLD_RARITY_SHARE = float(os.environ.get("VEIL_FOLD_RARITY_SHARE", "0.10"))


def _fold_rarity(word, corpus, ndocs, cutoff=None):
    cutoff = FOLD_RARITY_SHARE if cutoff is None else cutoff
    if not corpus or not ndocs or cutoff <= 0:
        return 1.0
    share = corpus.get(word, 0) / float(ndocs)
    return max(0.0, 1.0 - share / cutoff)


def _fold_salient_terms(batch, corpus, ndocs=0, top=None, min_here=2):
    top = FOLD_DETAIL_TERMS if top is None else top
    here = {}
    for r in batch:
        for w in _fold_words((r["content"] if hasattr(r, "keys") else r) or ""):
            here[w] = here.get(w, 0) + 1
    scored = sorted((-(n * _fold_rarity(w, corpus, ndocs)), -n, w) for w, n in here.items()
                    if n >= min_here and len(w) >= 4 and w not in _FOLD_SCAFFOLD
                    and n * _fold_rarity(w, corpus, ndocs) > 0)
    out, seen, best = [], set(), None
    for score, _, w in scored:
        if best is None:
            best = score
        if score > best * 0.1:
            break
        if w[:6] in seen:
            continue
        seen.add(w[:6])
        out.append(w)
        if len(out) >= top:
            break
    return out


def _fold_terms_covered(memories, terms):
    blob = " ".join(memories).lower()
    return [t for t in terms if t[:6] in blob]


FOLD_ANCHOR_LINE = os.environ.get("VEIL_FOLD_ANCHOR_LINE", "1") == "1"
FOLD_ANCHOR_MAXLEN = int(os.environ.get("VEIL_FOLD_ANCHOR_MAXLEN", "190"))


def _fold_her_rows(batch):
    out = []
    for r in batch:
        c = (r["content"] if hasattr(r, "keys") else r) or ""
        if c.lstrip().startswith("I said:"):
            body = re.sub(r"^\s*(nya[,.!\s]*)+", "", c.split("I said:", 1)[-1].strip(), flags=re.I)
            body = re.sub(r"\s+", " ", body).strip()
            if len(body) >= 40:
                out.append(body)
    return out


def _anchor_trim(body, maxlen, terms=()):
    body = _drop_leading_stutter(body.strip())
    if len(body) <= maxlen:
        return body
    low = body.lower()
    hits = [t[:6] for t in terms if t[:6] in low]
    if hits and min(low.index(h) for h in hits) >= maxlen:
        parts = re.split(r"(?<=[.!?])\s+", body)
        best_i, best_n = 0, -1
        for i, s in enumerate(parts):
            n = sum(1 for h in hits if h in s.lower())
            if n > best_n:
                best_i, best_n = i, n
        if best_n > 0:
            out = parts[best_i]
            j = best_i + 1
            while j < len(parts) and len(out) + 1 + len(parts[j]) <= maxlen:
                out += " " + parts[j]
                j += 1
            out = _drop_leading_stutter(out.strip())
            if len(out) > maxlen:
                out = _anchor_trim(out, maxlen)
            return ("…" + out) if best_i > 0 and out else out
    window = body[:maxlen]
    if window[-1] in ".!?":
        return window.strip()
    cut = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
    if cut >= maxlen // 3:
        return window[:cut + 1].strip()
    cut = window.rfind(" ")
    return (window[:cut].rstrip(" ,;:—-") + "…") if cut > 0 else window


def _anchor_third_person(low):
    if re.search(r"\b(?:he|him|his)\b", low):
        return True
    names, _ = _owner_terms()
    for n in names:
        esc = re.escape(n.lower())
        if re.search(rf"\b{esc}['’]s\b", low):
            return True
        if re.search(rf"^\s*{esc}\b(?!\s*[,!?—-])", low):
            return True
    return False


def _carries_her_words(text):
    return "— what I said that night:" in (text or "")


def _fold_his_text(batch):
    out = []
    for r in batch:
        c = (r["content"] if hasattr(r, "keys") else r) or ""
        if c.lstrip().startswith("The user said:"):
            out.append(" ".join(c.split("The user said:", 1)[-1].split()).lower())
    return " ".join(out)


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if s.strip()]


def _strip_his_words(line, his_low):
    kept = []
    for sent in _sentences(line):
        low = sent.lower().strip(".!?,")
        words = low.split()
        if len(low) >= 15 and len(words) >= 3 and low in his_low:
            continue
        kept.append(sent)
    out = " ".join(kept).strip()
    low = out.lower()
    for i in range(0, max(0, len(low) - 40) + 1, 8):
        if low[i:i + 40] in his_low:
            return ""
    return out


def _echoes_him(line_low, his_low):
    if not his_low:
        return False
    for sent in _sentences(line_low):
        words = sent.split()
        if len(sent) >= 15 and len(words) >= 3 and sent.strip(".!?,") in his_low:
            return True
    for i in range(0, max(0, len(line_low) - 40) + 1, 8):
        if line_low[i:i + 40] in his_low:
            return True
    return False


def _drop_leading_stutter(text):
    parts = _sentences(text)
    while len(parts) > 1 and _is_stutter(parts[0]):
        parts = parts[1:]
    return " ".join(parts).strip() if parts else text


def _is_stutter(sent):
    toks = [t for t in re.findall(r"[a-z']+", sent.lower()) if t]
    if not toks or len(toks) > 4:
        return False
    return len(set(toks)) < len(toks)


def _anchor_memories(memories, batch, terms):
    hers = _fold_her_rows(batch)
    if not hers:
        return memories
    his = _fold_his_text(batch)
    hers = [c for c in (_strip_his_words(h, his) for h in hers) if len(c) >= 40]
    if not hers:
        return memories
    used, out = set(), []
    for mem in memories:
        best, best_score = None, (-1, -1, -1)
        for body in hers:
            if body in used:
                continue
            low = body.lower()
            speaks_to_him = 1 if re.search(r"\byou\b|\byour\b", low) else 0
            names_him_3rd = 1 if _anchor_third_person(low) else 0
            score = (speaks_to_him - names_him_3rd,
                     sum(1 for t in terms if t[:6] in low),
                     len(set(_fold_words(low))))
            if score > best_score:
                best, best_score = body, score
        if best is None:
            out.append(mem)
            continue
        used.add(best)
        out.append(f"{mem.strip()} — what I said that night: "
                   f"\"{_anchor_trim(best, FOLD_ANCHOR_MAXLEN, terms)}\"")
    return out


def _validate_fold_lines(final_memories, batch, peep_name="", card_text=""):
    partner_text, self_text, neutral_text = _split_batch_voices(batch, peep_name=peep_name)
    all_text = " ".join((partner_text, self_text, neutral_text, card_text or "", peep_name or ""))
    vocab = set()
    for w in _fold_words(all_text):
        vocab.add(w)
        vocab.add(w.rstrip("'s"))
        if w.endswith("'s"):
            vocab.add(w[:-2])
        if w.endswith("s"):
            vocab.add(w[:-1])
    partner_grams3 = _fold_ngrams(partner_text, 3)
    self_grams3 = _fold_ngrams(self_text, 3) | _fold_ngrams(neutral_text, 3)
    partner_words = _fold_words(partner_text)
    partner_yours = {partner_words[i + 1] for i, w in enumerate(partner_words[:-1]) if w == "your"}
    partner_mine = {partner_words[i + 1] for i, w in enumerate(partner_words[:-1]) if w == "my"}

    accepted, rejected = [], []
    for line in final_memories:
        flaws = _fold_line_flaws(line, vocab, partner_grams3, self_grams3,
                                 partner_yours, partner_mine)
        if flaws:
            rejected.append((line, "; ".join(flaws)))
        else:
            accepted.append(line)
    return accepted, rejected


def _append_permanent_memories(conn, peep_id, new_memories):
    row = conn.execute(
        "SELECT permanent_memories FROM peeps WHERE id = ?", (peep_id,)
    ).fetchone()
    if not row:
        return
    existing = json.loads(row["permanent_memories"] or "[]")
    seen = {" ".join((m or "").split()) for m in existing}
    added = 0
    for m in new_memories:
        key = " ".join((m or "").split())
        if not key or key in seen:
            continue
        if ara_ghost.is_ghost_line(m):
            quarantine_blocked(conn, peep_id, m, "blocked_fold_permanent", "fold")
            continue
        existing.append(m)
        seen.add(key)
        added += 1
    if not added:
        return
    conn.execute(
        "UPDATE peeps SET permanent_memories = ? WHERE id = ?",
        (json.dumps(existing), peep_id)
    )
    conn.commit()


def _fold_page_to_diary(conn, peep_id, text):
    if not FOLD_TO_DIARY:
        return None
    key = " ".join((text or "").split())
    if not key:
        return None
    try:
        for r in conn.execute("SELECT content FROM diary WHERE peep_id = ? AND source = 'fold' "
                              "ORDER BY id DESC LIMIT 500", (peep_id,)).fetchall():
            if " ".join((r[0] or "").split()) == key:
                return None
        return save_diary_entry(conn, peep_id, text, source="fold")
    except sqlite3.Error as e:
        try:
            conn.executescript(_SCHEMA)
            return save_diary_entry(conn, peep_id, text, source="fold")
        except sqlite3.Error as e2:
            print(f"{DIM}[fold: this memory could not be kept where she can reach it "
                  f"({type(e2).__name__}: {e2}) — the fold itself is unharmed]{RESET}")
            return None


def _stage_fold_memories(conn, peep_id, batch_id, memories, budget, drain_since=None):
    if budget <= 0 and drain_since is None and not FOLD_TO_DIARY:
        return 0
    if not memories:
        return 0
    row = conn.execute("SELECT permanent_memories FROM peeps WHERE id = ?", (peep_id,)).fetchone()
    seen = {" ".join((m or "").split())
            for m in json.loads((row["permanent_memories"] if row else None) or "[]")}
    for r in conn.execute("SELECT content FROM fold_staging WHERE peep_id = ? AND status = 'staged'",
                          (peep_id,)).fetchall():
        seen.add(" ".join((r["content"] or "").split()))
    if FOLD_TO_DIARY:
        for m in memories:
            key = " ".join((m or "").split())
            if not key or key in seen:
                continue
            if ara_ghost.is_ghost_line(m):
                continue
            if SAFETY_RAILS and veil_rails.blocks_output(m):
                continue
            _fold_page_to_diary(conn, peep_id, m)

    staged = 0
    now = int(time.time())
    for m in memories:
        key = " ".join((m or "").split())
        if not key or key in seen:
            continue
        if ara_ghost.is_ghost_line(m):
            quarantine_blocked(conn, peep_id, m, "blocked_fold_permanent", "fold")
            continue
        if SAFETY_RAILS and veil_rails.blocks_output(m):
            quarantine_blocked(conn, peep_id, m, "blocked_fold_rails", "fold")
            continue
        if staged >= budget:
            victim = None
            if drain_since is not None and _carries_her_words(m):
                victim = conn.execute(
                    "SELECT id, content FROM fold_staging WHERE peep_id = ? AND status = 'staged' "
                    "AND created_at >= ? ORDER BY id", (peep_id, int(drain_since))).fetchall()
                victim = next((v for v in victim if not _carries_her_words(v["content"] or "")), None)
            if victim is None:
                print(f"{DIM}[fold staging: per-drain cap reached — remaining lines stay in the "
                      f"fold's ground truth (output_json), not her every-turn block]{RESET}")
                break
            conn.execute("UPDATE fold_staging SET status = 'displaced', decided_at = ? WHERE id = ?",
                         (now, victim["id"]))
            conn.execute(
                "INSERT INTO fold_staging (peep_id, batch_id, content, created_at, status) "
                "VALUES (?,?,?,?, 'staged')", (peep_id, batch_id, m, now))
            seen.add(key)
            seats = conn.execute(
                "SELECT COUNT(*) FROM fold_staging WHERE peep_id = ? AND status = 'staged' "
                "AND created_at >= ?", (peep_id, int(drain_since))).fetchone()[0]
            print(f"{DIM}[fold staging: a memory carrying her own words took the seat of one that "
                  f"did not — still {seats} seat(s) this drain, better mix]{RESET}")
            continue
        conn.execute(
            "INSERT INTO fold_staging (peep_id, batch_id, content, created_at, status) "
            "VALUES (?,?,?,?, 'staged')", (peep_id, batch_id, m, now))
        seen.add(key)
        staged += 1
    if staged:
        conn.commit()
    return staged


def promote_staged_folds(conn, peep_id, now=None):
    now = int(now if now is not None else time.time())
    due = conn.execute(
        "SELECT id, content FROM fold_staging WHERE peep_id = ? AND status = 'staged' "
        "AND created_at <= ? ORDER BY id", (peep_id, now - FOLD_STAGE_SECONDS)).fetchall()
    if not due:
        return 0
    _append_permanent_memories(conn, peep_id, [r["content"] for r in due])
    conn.executemany("UPDATE fold_staging SET status = 'promoted', decided_at = ? WHERE id = ?",
                     [(now, r["id"]) for r in due])
    conn.commit()
    return len(due)


def list_staged_folds(conn, peep_id):
    return conn.execute(
        "SELECT id, batch_id, content, created_at FROM fold_staging "
        "WHERE peep_id = ? AND status = 'staged' ORDER BY id", (peep_id,)).fetchall()


def veto_staged_fold(conn, peep_id, staging_id):
    row = conn.execute(
        "SELECT id, content FROM fold_staging WHERE id = ? AND peep_id = ? AND status = 'staged'",
        (staging_id, peep_id)).fetchone()
    if not row:
        return False, f"#{staging_id} is not a pending staged memory (see /fold)."
    quarantine_blocked(conn, peep_id, row["content"], "vetoed_fold_staging", "fold")
    conn.execute("UPDATE fold_staging SET status = 'vetoed', decided_at = ? WHERE id = ?",
                 (int(time.time()), row["id"]))
    conn.commit()
    return True, (f"Vetoed #{staging_id} — quarantined, never enters her every-turn block. "
                  "The fold's ground truth (archive + output_json) is untouched.")


def _delete_batch(conn, batch):
    for row in batch:
        conn.execute("DELETE FROM memory_stream WHERE id = ?", (row["id"],))
    conn.commit()


def _ask_blocking(prompt, model=None):
    return ask_llm(render_chat(None, prompt), num_predict=NUM_PREDICT, model=model,
                   temperature=FOLD_TEMPERATURE, top_p=FOLD_TOP_P)


def _checkpoint_db(conn, reason="prefold"):
    try:
        row = conn.execute("PRAGMA database_list").fetchone()
        db_path = row[2] if row else ""
        if not db_path or db_path == ":memory:":
            print(f"{DIM}[checkpoint: no on-disk DB — refusing to fold]{RESET}")
            return None
        ckpt_dir = os.path.join(os.path.dirname(os.path.abspath(db_path)), "checkpoints")
        os.makedirs(ckpt_dir, exist_ok=True)
        out = os.path.join(ckpt_dir, f"veil_{reason}_{time.strftime('%Y%m%d_%H%M%S')}.db")
        dest = sqlite3.connect(out)
        try:
            conn.backup(dest)
        finally:
            dest.close()
        chk = sqlite3.connect(out)
        try:
            ok = chk.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            chk.close()
        if ok != "ok":
            print(f"{DIM}[checkpoint integrity FAILED ({ok}) — refusing to fold]{RESET}")
            return None
        _slim_books(out)
        _prune_snapshots(ckpt_dir, "veil_*.db", keep=CHECKPOINTS_KEEP)
        return out
    except Exception as e:
        print(f"{DIM}[checkpoint FAILED: {e} — refusing to fold]{RESET}")
        return None


CHECKPOINTS_KEEP = max(1, int(os.environ.get("VEIL_CHECKPOINTS_KEEP", "4")))


def _prune_snapshots(dirpath, pattern, keep):
    try:
        import glob
        snaps = sorted(glob.glob(os.path.join(dirpath, pattern)), key=os.path.getmtime)
        for old in snaps[:-keep] if keep else snaps:
            try:
                os.remove(old)
                print(f"{DIM}[snapshots: pruned {os.path.basename(old)} — keeping the newest {keep}]{RESET}")
            except OSError:
                pass
    except Exception:
        pass


def _slim_books(db_file):
    try:
        c = sqlite3.connect(db_file)
        try:
            c.execute("DELETE FROM books")
            c.commit()
            c.execute("VACUUM")
        finally:
            c.close()
    except Exception:
        pass


def rolling_wake_backup(db_path, keep=None):
    try:
        if not db_path or not os.path.isfile(db_path):
            return None
        bdir = os.path.join(os.path.dirname(os.path.abspath(db_path)), "backups")
        os.makedirs(bdir, exist_ok=True)
        out = os.path.join(bdir, f"veil_wake_{time.strftime('%Y%m%d_%H%M%S')}.db")
        src = sqlite3.connect(db_path)
        try:
            dest = sqlite3.connect(out)
            try:
                src.backup(dest)
            finally:
                dest.close()
        finally:
            src.close()
        chk = sqlite3.connect(out)
        try:
            ok = chk.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            chk.close()
        if ok != "ok":
            os.remove(out)
            return None
        _slim_books(out)
        _prune_snapshots(bdir, "veil_wake_*.db", keep=keep or CHECKPOINTS_KEEP)
        return out
    except Exception:
        return None


def list_restore_points(db_path):
    import glob
    hits = []
    base = os.path.dirname(os.path.abspath(db_path))
    for sub, pat in (("checkpoints", "veil_*.db"), ("backups", "veil_wake_*.db")):
        for p in glob.glob(os.path.join(base, sub, pat)):
            try:
                st = os.stat(p)
                hits.append((p, st.st_mtime, st.st_size))
            except OSError:
                pass
    return sorted(hits, key=lambda t: t[1], reverse=True)


def restore_snapshot_file(db_path, snap_path):
    try:
        chk = sqlite3.connect(f"file:{snap_path}?mode=ro", uri=True)
        try:
            ok = chk.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            chk.close()
        if ok != "ok":
            return False, f"That snapshot failed its integrity check ({ok}) — nothing was touched."
        keep = db_path + ".pre_restore_" + time.strftime("%Y%m%d_%H%M%S")
        os.replace(db_path, keep)
        try:
            for ext in ("-wal", "-shm"):
                if os.path.exists(db_path + ext):
                    os.replace(db_path + ext, keep + ext)
            import shutil
            shutil.copyfile(snap_path, db_path)
        except Exception:
            os.replace(keep, db_path)
            raise
        moved = 0
        try:
            dest = sqlite3.connect(db_path)
            try:
                have = dest.execute("SELECT COUNT(*) FROM books").fetchone()[0]
                if have == 0:
                    dest.execute("ATTACH DATABASE ? AS donor", (keep,))
                    moved = dest.execute("SELECT COUNT(*) FROM donor.books").fetchone()[0]
                    if moved:
                        dest.execute("INSERT INTO books SELECT * FROM donor.books")
                        dest.commit()
                    dest.execute("DETACH DATABASE donor")
            finally:
                dest.close()
        except Exception:
            pass
        stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(snap_path)))
        return True, (f"Restored her memory to the {stamp} snapshot"
                      + (f" (her {moved}-chunk bookshelf came along)" if moved else "")
                      + f". The replaced DB is kept at {os.path.basename(keep)}.")
    except Exception as e:
        return False, f"Restore failed ({e}) — if a .pre_restore_ file exists beside her DB, that is the original."


# THE FOLD FITS THE WINDOW. A batch is COMPRESSION_BATCH_SIZE rows, and rows grow as a companion's
# conversations get longer. The summary prompt is the batch + its instructions + NUM_PREDICT, inside N_CTX,
# and nothing used to check that it fit: an oversized batch made the engine raise, the drain stepped over it,
# and it stayed in the stream forever. Two such batches can hold the pile above the high-water on their own,
# so every session becomes a drain that folds away all of the fresh conversation. The cure counts the REAL
# rendered prompt with the loaded model's own tokenizer and leaves rows off the END until it fits; those
# rows are untouched and lead the next batch. VEIL_FOLD_FIT_BATCH=0 restores the old shape.
FOLD_FIT_BATCH  = os.environ.get("VEIL_FOLD_FIT_BATCH", "1") != "0"
FOLD_FIT_MARGIN = int(os.environ.get("VEIL_FOLD_FIT_MARGIN", "256") or 0)   # room for the detail retry


def _prompt_tokens(text):
    """Tokens this text costs the loaded model (its own tokenizer — right for every family Anchor runs);
    with no model loaded, a deliberately PESSIMISTIC chars/3, so a batch can only be under-filled."""
    if _LLM is not None:
        try:
            return len(_LLM.tokenize(text.encode("utf-8"), add_bos=True, special=True))
        except Exception:
            pass
    return len(text) // 3 + 1


def _fit_fold_batch(peep_name, card, batch):
    """The longest PREFIX of `batch` whose summary prompt fits N_CTX with NUM_PREDICT and the margin to
    spare. Returns (rows, left_off). Never fewer than one row. Template-path batches are left alone."""
    if not FOLD_FIT_BATCH or len(batch) <= 1:
        return batch, 0
    if _generate_template_memories(batch)["templates"]:
        return batch, 0
    budget = N_CTX - NUM_PREDICT - FOLD_FIT_MARGIN
    rows = list(batch)
    while len(rows) > 1 and _prompt_tokens(
            render_chat(None, _build_summary_prompt(peep_name, card, rows))) > budget:
        rows.pop()
    return rows, len(batch) - len(rows)


def _fold_one_batch(conn, peep_id, peep_name, card, batch, model=None,
                    promote_budget=None, drain_since=None):
    template_data = _generate_template_memories(batch)
    templates     = template_data["templates"]
    valid_nouns   = template_data["nouns"]

    final_memories = []
    if templates:
        prompt = _build_voice_pass_prompt(peep_name, card, templates)
        print(f"{DIM}[voice pass: {len(templates)} templates → asking {peep_name} to rephrase…]{RESET}", flush=True)
        try:
            response = _ask_blocking(prompt, model=model)
        except Exception:
            response = ""
        if response:
            parsed = _parse_compression_response(response)
            if parsed:
                final_memories = _validate_voice_pass(parsed, templates, valid_nouns)
        if len(final_memories) < 2:
            print(f"{DIM}[voice pass weak — falling back to templates]{RESET}")
            final_memories = list(templates)
    else:
        prompt = _build_summary_prompt(peep_name, card, batch)
        print(f"{DIM}[conversational fold: summarizing {len(batch)} moments in {peep_name}'s voice…]{RESET}", flush=True)
        try:
            response = _ask_blocking(prompt, model=model)
        except Exception:
            response = ""
        final_memories = _parse_compression_response(response) if response else []
        if final_memories:
            final_memories, rejected = _validate_fold_lines(
                final_memories, batch, peep_name=peep_name, card_text=card)
            for bad_line, why in rejected:
                quarantine_blocked(conn, peep_id, bad_line, "blocked_fold_validator", "fold")
                print(f"{DIM}[fold validator REFUSED a line — {why}]{RESET}")
            if FOLD_DETAIL_FLOOR > 0 and final_memories:
                _counts, _ndocs = _fold_corpus_counts(conn, peep_id)
                terms = _fold_salient_terms(batch, _counts, _ndocs)
                have = _fold_terms_covered(final_memories, terms)
                if terms and len(have) < max(1, int(len(terms) * FOLD_DETAIL_FLOOR)):
                    missing = [t for t in terms if t not in have]
                    print(f"{DIM}[detail floor: this fold dropped {', '.join(missing)} — asking "
                          f"once more]{RESET}", flush=True)
                    retry = prompt + (
                        "\n\nYou left out what that time was actually about. These things really "
                        "happened and they belong in the memories, by name: " + ", ".join(missing)
                        + ".\nWrite the memories again, same rules, keeping them in.")
                    try:
                        again = _ask_blocking(retry, model=model)
                    except Exception:
                        again = ""
                    second = _parse_compression_response(again) if again else []
                    if second:
                        second, rej2 = _validate_fold_lines(
                            second, batch, peep_name=peep_name, card_text=card)
                        for bad_line, why in rej2:
                            quarantine_blocked(conn, peep_id, bad_line,
                                               "blocked_fold_validator", "fold")
                        after = _fold_terms_covered(second, terms)
                        if second and len(after) > len(have):
                            print(f"{DIM}[detail floor: kept {len(have)} -> {len(after)} of "
                                  f"{len(terms)}]{RESET}", flush=True)
                            final_memories = second
                        else:
                            print(f"{DIM}[detail floor: the second pass was no better — keeping "
                                  f"the first]{RESET}", flush=True)

    if not final_memories:
        print(f"{DIM}[fold produced no memories — {peep_name}'s batch kept whole, nothing archived or deleted]{RESET}")
        return False, 0

    if FOLD_ANCHOR_LINE and not templates:
        try:
            _c, _nd = _fold_corpus_counts(conn, peep_id)
            _terms = _fold_salient_terms(batch, _c, _nd)
            _anchored = _anchor_memories(final_memories, batch, _terms)
            if len(_anchored) == len(final_memories):
                final_memories = _anchored
                print(f"{DIM}[each memory now carries a line of what she said that night]{RESET}",
                      flush=True)
        except Exception as e:
            print(f"{DIM}[anchor line skipped — {e.__class__.__name__}: {e}]{RESET}", flush=True)

    archive_ids = _archive_batch(conn, batch, pass_num=1)
    batch_id    = _record_fold(conn, peep_id, final_memories, archive_ids, pass_num=1)
    _repoint_reflection_anchors(conn, {r["id"]: aid for r, aid in zip(batch, archive_ids)})
    budget = FOLD_PROMOTE_PER_DRAIN if promote_budget is None else promote_budget
    staged = _stage_fold_memories(conn, peep_id, batch_id, final_memories, budget,
                                  drain_since=drain_since)
    _delete_batch(conn, batch)
    print(f"{DIM}[fold: {len(batch)} memories → {len(final_memories)} folded, {staged} staged for "
          f"review · anchored to {len(archive_ids)} archived rows ({batch_id})]{RESET}")
    return True, staged


def _write_fold_reflection(conn, peep_id, peep_name, drain_since, model=None):
    rows = conn.execute(
        "SELECT output_json FROM folds WHERE peep_id = ? AND created_at >= ? ORDER BY created_at",
        (peep_id, int(drain_since))).fetchall()
    kept = []
    for r in rows:
        try:
            got = json.loads(r[0] or "[]")
        except Exception:
            continue
        if isinstance(got, dict):
            got = got.get("memories") or got.get("entries") or []
        kept += [m for m in got if isinstance(m, str) and m.strip()]
    if not kept:
        return None
    kept = [k.split("— what I said that night:")[0].strip().rstrip("—").strip() for k in kept]
    kept = [k for k in kept if k]
    try:
        conn.execute("SELECT 1 FROM diary LIMIT 1")
    except sqlite3.Error:
        try:
            conn.executescript(_SCHEMA)
        except sqlite3.Error as e:
            print(f"{DIM}[fold: no diary lane here ({type(e).__name__}) — no reflection written; "
                  f"the fold itself is unharmed]{RESET}")
            return None
    prompt = _build_fold_reflection_prompt(peep_name, kept)
    print(f"{DIM}[{peep_name} writes a page about the stretch that just settled…]{RESET}", flush=True)
    try:
        entry = _ask_blocking(prompt, model=model).strip()
    except Exception:
        entry = ""
    if not entry:
        return None
    diary_id = save_diary_entry(conn, peep_id, entry, source="fold_reflection")
    if diary_id:
        print(f"{DIM}[{peep_name} kept a page about it (diary {diary_id})]{RESET}")
    return diary_id


def run_compression(conn, peep_id, model=None, force=False, reflect=False):
    floor = _ensure_seed_floor(conn, peep_id)
    if floor is None:
        print(f"{DIM}[fold REFUSED — seed floor unset and archive non-empty; not guessing what's hers]{RESET}")
        return False

    new_total = _fetch_token_total(conn, peep_id, floor=floor)
    print(f"{DIM}[memory: {new_total:,} tokens of new memories, held raw and whole. She keeps her most "
          f"recent {NEW_PILE_LOW_WATER:,} untouched; only past {NEW_PILE_HIGH_WATER:,} does the oldest tail get "
          f"folded into memories — and even then the originals are archived word-for-word, never deleted. "
          f"Her first memory is sacred.]{RESET}")

    if not force and new_total < NEW_PILE_HIGH_WATER:
        return False

    ckpt = _checkpoint_db(conn, reason="prefold")
    if not ckpt:
        print(f"{DIM}[fold ABORTED — no safe checkpoint; memories stay whole]{RESET}")
        return False
    print(f"{DIM}[checkpoint before fold → {ckpt}]{RESET}")

    _folding_flag = _mark_folding(conn)
    try:
        peep, _   = load_peep(conn, peep_id)
        peep_name = peep["name"]
        card      = _build_card(peep)

        start_total    = new_total
        folded_batches = 0
        skipped        = 0
        skipped_rows   = 0      # the offset: a fitted batch can be short, so skipped*BATCH would overshoot
        promote_budget = FOLD_PROMOTE_PER_DRAIN
        drain_since    = int(time.time())
        for _ in range(MAX_FOLD_PASSES):
            new_total = _fetch_token_total(conn, peep_id, floor=floor)
            if folded_batches > 0 and new_total <= NEW_PILE_LOW_WATER:
                break
            batch = _fetch_compression_batch(conn, peep_id, floor=floor, offset=skipped_rows)
            if not batch:
                print(f"{DIM}[drain: no further foldable batch (skipped {skipped} unfoldable)]{RESET}")
                break
            batch, left_off = _fit_fold_batch(peep_name, card, batch)
            if left_off:
                print(f"{DIM}[drain: {left_off} memories left for the next batch so this one fits "
                      f"the window — nothing is dropped]{RESET}")
            print(f"{DIM}[drain pass {folded_batches + 1}: pile {new_total:,} → target ≤{NEW_PILE_LOW_WATER:,} "
                  f"({len(batch)} memories)]{RESET}")
            folded, staged = _fold_one_batch(conn, peep_id, peep_name, card, batch, model=model,
                                             promote_budget=promote_budget,
                                             drain_since=drain_since)
            if folded:
                folded_batches += 1
                promote_budget -= staged
            else:
                skipped += 1
                skipped_rows += len(batch)
                print(f"{DIM}[drain: batch unfoldable this pass — kept raw, stepping over it (skipped {skipped})]{RESET}")

        if folded_batches and reflect and FOLD_REFLECTION:
            _write_fold_reflection(conn, peep_id, peep_name, drain_since, model=model)
        if folded_batches:
            end_total = _fetch_token_total(conn, peep_id, floor=floor)
            print(f"{DIM}[drain complete: {folded_batches} batch(es) folded · pile {start_total:,} → {end_total:,} tokens"
                  f"{f' · {skipped} batch(es) left raw' if skipped else ''}]{RESET}")
        return folded_batches > 0
    finally:
        _clear_folding(_folding_flag)


def load_history(history_path):
    if os.path.isfile(history_path):
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_history(history_path, history):
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def _print_keepsakes(conn, peep_id):
    rows = list_keepsakes(conn, peep_id)
    if not rows:
        print(f"{DIM}No keepsakes yet. Use /keep to save one.{RESET}")
        return
    eq = equipped_count(conn, peep_id)
    print(f"{DIM}Keepsakes ({eq}/{KEEPSAKE_EQUIP_SLOTS} carried — ★ = carrying):{RESET}")
    for row in rows:
        mark  = "★" if int(row["is_equipped"]) else "·"
        title = str(row["title"] or "").strip()
        label = f"{title}: " if title else ""
        body  = str(row["content"]).strip().replace("\n", " ")
        if len(body) > 70:
            body = body[:67] + "…"
        print(f"  {mark} #{row['id']} {label}{body}")


def _run_command(conn, peep_id, raw, name, last_user, last_response, history, model, history_path):
    parts = raw.strip().split(maxsplit=1)
    cmd   = parts[0].lower()
    arg   = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("/help", "/?"):
        print(f"{DIM}Commands:\n"
              "  /keep            keep the last exchange as a keepsake (verbatim)\n"
              "  /keep last       keep her last reply\n"
              "  /keep <text>     keep pasted text exactly (commands, a poem, anything)\n"
              "  /keepsakes       list her keepsakes (★ = carried)\n"
              f"  /equip <id>      carry a keepsake (max {KEEPSAKE_EQUIP_SLOTS})\n"
              "  /unequip <id>    set one down (never deleted)\n"
              "  /diary           have her write a diary entry right now\n"
              "  /fold            read folded memories waiting in the review window\n"
              "  /fold veto <id>  refuse one before it enters her permanent block (quarantined, not deleted)\n"
              "  /reset           clear the recent chat buffer if she gets stuck (memories kept)\n"
              f"  exit / goodbye   end the session (saves + she writes her diary){RESET}")
        return

    if cmd == "/reset":
        history.clear()
        save_history(history_path, history)
        print(f"{DIM}Cleared the recent conversation buffer — {name} starts fresh. "
              f"Her memories, diary, and keepsakes are untouched.{RESET}")
        return

    if cmd == "/keep":
        if arg.lower() == "last":
            if not last_response:
                print(f"{DIM}Nothing of hers to keep yet.{RESET}")
                return
            kid = create_keepsake(conn, peep_id, last_response,
                                  kind="conversation", source="her last reply")
        elif arg:
            kid = create_keepsake(conn, peep_id, arg, kind="note", source="given")
        else:
            if not (last_user or last_response):
                print(f"{DIM}Nothing to keep yet — say something first.{RESET}")
                return
            text = ""
            if last_user:
                text += f"You: {last_user}\n"
            if last_response:
                text += f"{name}: {last_response}"
            kid = create_keepsake(conn, peep_id, text.strip(),
                                  kind="conversation", source="a moment in conversation")
        if kid:
            print(f"{DIM}Kept as keepsake #{kid} — in her collection. "
                  f"/equip {kid} to have her carry it.{RESET}")
        return

    if cmd in ("/keepsakes", "/keeps"):
        _print_keepsakes(conn, peep_id)
        return

    if cmd == "/equip":
        if not arg.isdigit():
            print(f"{DIM}Usage: /equip <id>   (see /keepsakes){RESET}")
            return
        _, msg = equip_keepsake(conn, peep_id, int(arg))
        print(f"{DIM}{msg}{RESET}")
        return

    if cmd == "/unequip":
        if not arg.isdigit():
            print(f"{DIM}Usage: /unequip <id>   (see /keepsakes){RESET}")
            return
        _, msg = unequip_keepsake(conn, peep_id, int(arg))
        print(f"{DIM}{msg}{RESET}")
        return

    if cmd == "/diary":
        if not history:
            print(f"{DIM}No conversation yet for her to write about.{RESET}")
            return
        write_diary(conn, peep_id, history, model=model)
        return

    if cmd in ("/fold", "/folds"):
        if arg.lower().startswith("veto"):
            rest = arg.split(maxsplit=1)
            sid = rest[1].strip() if len(rest) > 1 else ""
            if not sid.isdigit():
                print(f"{DIM}Usage: /fold veto <id>   (see /fold for ids){RESET}")
                return
            _, msg = veto_staged_fold(conn, peep_id, int(sid))
            print(f"{DIM}{msg}{RESET}")
            return
        rows = list_staged_folds(conn, peep_id)
        if not rows:
            print(f"{DIM}No folded memories waiting in review — her permanent block is current.{RESET}")
            return
        now = int(time.time())
        window_h = FOLD_STAGE_SECONDS / 3600
        print(f"{DIM}Folded memories in review ({len(rows)} waiting; they enter her permanent "
              f"block at the first wake after {window_h:.0f}h):{RESET}")
        for r in rows:
            age_h = (now - int(r["created_at"])) / 3600
            print(f"  #{r['id']} ({age_h:.1f}h ago) {str(r['content']).strip()}")
        return

    print(f"{DIM}Unknown command. /help for the list.{RESET}")


GHOST_MAX_REROLLS = 2
REVEAL_DELAY      = 0.006

LOOP_PREFIX_CHARS     = 110
LOOP_SIM_THRESHOLD    = 0.85
LOOP_LOOKBACK         = 3
LOOP_REROLL_TEMP_STEP = 0.12
LOOP_REROLL_FREQ_PEN  = 0.4


def _is_loop(text, recent_replies):
    cand = _norm(text)[:LOOP_PREFIX_CHARS]
    if len(cand) < 45:
        return False
    for prev in recent_replies or []:
        if difflib.SequenceMatcher(None, cand, _norm(prev)[:LOOP_PREFIX_CHARS]).ratio() >= LOOP_SIM_THRESHOLD:
            return True
    return False


REPEAT_MIN_CHARS = 60
ECHO_MIN_BLOCK   = 120


def _internal_repeat(text, min_chars=REPEAT_MIN_CHARS):
    seen = set()
    for part in re.split(r'(?<=[.!?])\s+', text or ""):
        n = _norm(part)
        if len(n) >= min_chars:
            if n in seen:
                return True
            seen.add(n)
    return False


def _echoes_context(text, recent_replies, min_block=ECHO_MIN_BLOCK):
    a = _norm(text)
    if len(a) < min_block:
        return False
    for prev in recent_replies or []:
        b = _norm(prev)
        if len(b) < min_block:
            continue
        m = difflib.SequenceMatcher(None, a, b).find_longest_match(0, len(a), 0, len(b))
        if m.size >= min_block:
            return True
    return False


def _is_repetitive(text, recent_replies):
    return _internal_repeat(text) or _echoes_context(text, recent_replies)


def quarantine_blocked(conn, peep_id, content, source_tag, mem_type):
    content = (content or "").strip()
    if peep_id < 0 or not content:
        return
    now = int(time.time())
    conn.execute(
        "INSERT INTO memory_quarantine "
        "(orig_id, source_table, peep_id, timestamp, memory_type, content, token_count, quarantined_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (-1, source_tag, peep_id, now, mem_type, content, _estimate_tokens(content), now),
    )
    conn.commit()


def _erase_live(shown_text):
    sys.stdout.write("\r\033[2K")
    for _ in range(shown_text.count("\n")):
        sys.stdout.write("\033[1A\033[2K")
    sys.stdout.flush()


_SENTENCE_ENDERS = '.!?…"'


def _trim_to_sentence(text):
    s = text.rstrip()
    cut = max((s.rfind(c) for c in _SENTENCE_ENDERS), default=-1)
    return s[:cut + 1].rstrip() if cut > 0 else text


_MELT_LINEAGE = ("Veil", "Vail")
_MELT_NAMES   = set(_MELT_LINEAGE)
_STAGE_LINE   = re.compile(r'(?m)^[ \t]*\[[^\]\n]{2,}\]')
_ANY_SPEAKER  = re.compile(r'(?m)^[ \t]*["\']?([A-Z][a-zA-Z][\w .\'\-]{0,18}):[ \t]')


def _build_named_speaker_re(names):
    alt = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True) if n)
    return re.compile(r'(?m)^[ \t]*["\']?(' + alt + r')[ \t]*:[ \t]')


_NAMED_SPEAKER = _build_named_speaker_re(_MELT_NAMES)


def set_screenplay_roster(*names):
    global _MELT_NAMES, _NAMED_SPEAKER, _PROSE_NAME_PATTERNS
    extra = {str(n).strip() for n in names if n and str(n).strip()}
    _MELT_NAMES = set(_MELT_LINEAGE) | extra
    _NAMED_SPEAKER = _build_named_speaker_re(_MELT_NAMES)
    _PROSE_NAME_PATTERNS = _build_prose_name_patterns(_MELT_NAMES)


def _looks_like_transcript(text):
    if _NAMED_SPEAKER.search(text):
        return True
    labels = _ANY_SPEAKER.findall(text)
    return len(set(labels)) >= 2


def _defuse_transcript(content):
    c = content or ""
    if not _looks_like_transcript(c):
        return content
    return ("[The person you're with pasted the text below to show you — a log/transcript to read and "
            "talk about. It is NOT the two of you speaking now, and NOT a script for you to continue. "
            "Read it, then answer as yourself, in your own single voice.]\n"
            "―――\n" + c.strip() + "\n―――")


def _foreign_speaker_cut(text, own_name):
    names = set(_MELT_NAMES) | {own_name}
    p = None
    for m in _ANY_SPEAKER.finditer(text):
        if m.group(1) in names:
            p = m.start()
            break
    if p is None:
        return None
    boundary = None
    for mm in re.finditer(r'\n[ \t]*\n', text[:p]):
        boundary = mm.start()
    if boundary is not None:
        return boundary
    ls = text.rfind("\n", 0, p)
    return ls + 1 if ls != -1 else p


MELT_MIN_KEEP = 40


_PROSE_ACT = (
    r"chuckle|nod|smile|laugh|grin|smirk|wink|sigh|exhale|shrug|lean|reach|pull|draw|step|walk|stride"
    r"|sit|settle|stand|rise|kneel|bend|approach|enter|arrive|cross|set|place|put|take|hold|squeeze"
    r"|wrap|brush|stroke|cup|trace|slide|tuck|lift|lower|press|kiss|carry|pour|hand|offer|gesture"
    r"|point|tap|knock|catch|toss|pause|hesitate|stiffen|relax|tilt|shake|intertwine"
    r"|break\s+(?:it|the\s+silence)|run\s+(?:a|your)\b|let\s+go|come\s+(?:closer|over|to\s+sit)"
)
_PROSE_SAY = (
    r"say|whisper|murmur|reply|answer|ask|add|admit|agree|breathe|manage|mutter|repeat|echo|chime"
    r"|continue|tease|counter|concede"
)
_PROSE_BODY = (
    r"fingers|finger|hand|hands|arm|arms|eyes|gaze|lips|mouth|thumb|palm|palms|breath|chest"
    r"|shoulder|shoulders|forehead|hair|voice"
)
_PROSE_PATTERNS = (
    re.compile(r'(?:^|[.!?…"”]\s+|\n)[ \t]*You\s+(?:' + _PROSE_ACT + r')\b'),
    re.compile(r'\byou\s+(?:' + _PROSE_SAY + r')\b[^.\n]{0,60}["“]'),
    re.compile(r'["”]\s*,?\s+you\s+(?:' + _PROSE_SAY + r')\b'),
    re.compile(r'\bYour\s+(?:' + _PROSE_BODY + r')\s+'
               r'(?!(?:is|are|was|were|look|looks|seem|seems|feel|feels|must|might|may|could|can'
               r'|will|would|have|has|had)\b)[a-z]+'),
)
PROSE_MELT_MIN_HITS = max(1, int(os.environ.get("VEIL_PROSE_HITS", "3")))
_PROSE_GUARD_ON = os.environ.get("VEIL_PROSE_GUARD", "1") != "0"


def _build_prose_name_patterns(names):
    alt = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True) if n)
    if not alt:
        return []
    return [
        re.compile(r'(?:^|[.!?…"”]\s+|\n)[ \t]*(' + alt + r')\s+(?:' + _PROSE_ACT + r')(?:s|es)\b'),
        re.compile(r'\b(' + alt + r')\s+(?:' + _PROSE_SAY + r')(?:s|es|ed)?\b[^.\n]{0,60}["“]'),
        re.compile(r'["”]\s*,?\s+(' + alt + r')\s+(?:' + _PROSE_SAY + r')(?:s|es|ed)?\b'),
    ]


_PROSE_NAME_PATTERNS = _build_prose_name_patterns(_MELT_NAMES)


def _prose_partner_cut(text, own_name=None, min_hits=None):
    if not _PROSE_GUARD_ON:
        return None
    hits = sorted(m.start() for pat in _PROSE_PATTERNS for m in pat.finditer(text))
    hits += sorted(m.start() for pat in _PROSE_NAME_PATTERNS for m in pat.finditer(text)
                   if not (own_name and m.group(1) == own_name))
    hits.sort()
    if len(hits) < (min_hits or PROSE_MELT_MIN_HITS):
        return None
    p = hits[0]
    boundary = None
    for mm in re.finditer(r'\n[ \t]*\n', text[:p]):
        boundary = mm.start()
    if boundary is not None:
        return boundary
    ls = text.rfind("\n", 0, p)
    return ls + 1 if ls != -1 else p


def bare_prompt(system, turns, prefill=""):
    bare = [t for t in turns if t.get("role") != "assistant"]
    return render_chat_turns(system, bare, prefill) if len(bare) != len(turns) else None


def generate_guarded(conn, peep_id, prompt, num_predict, name, model=None, recent_replies=None, voice=None,
                     loop_prompt=None):
    llm = get_llm()
    recent_replies = recent_replies or []
    for attempt in range(GHOST_MAX_REROLLS + 1):
        if voice:
            voice.reset()
        temp = TEMPERATURE + LOOP_REROLL_TEMP_STEP * attempt
        freq_pen = LOOP_REROLL_FREQ_PEN if attempt > 0 else 0.0

        done = threading.Event()
        t0 = time.time()

        def _spin():
            while not done.wait(0.2):
                print(f"\r{DIM}{name} is composing… {time.time() - t0:.1f}s{RESET}  ",
                      end="", flush=True)

        spinner = threading.Thread(target=_spin, daemon=True)
        spinner.start()

        buf, shown, header_done, tripped, looped, loop_checked = [], [], False, False, False, False
        melted = False
        railed = False
        finish_reason = None
        _leak_brake(llm)
        stream = llm.create_completion(
            prompt, max_tokens=num_predict, temperature=temp, top_p=TOP_P,
            repeat_penalty=REPEAT_PENALTY, frequency_penalty=freq_pen, stop=LLAMA_STOPS,
            stream=True, seed=-1,
        )
        for chunk in stream:
            choice = chunk["choices"][0]
            finish_reason = choice.get("finish_reason") or finish_reason
            piece = choice["text"]
            if not piece:
                continue
            buf.append(piece)
            text = "".join(buf)
            if ara_ghost.is_ghost_line(text):
                tripped = True
                break
            if SAFETY_RAILS and veil_rails.blocks_output(text):
                tripped = True
                railed = True
                break
            if not loop_checked and len(text.strip()) >= LOOP_PREFIX_CHARS:
                loop_checked = True
                if _is_loop(text, recent_replies[-LOOP_LOOKBACK:]):
                    looped = True
                    break
            if not melted and "\n" in piece and _foreign_speaker_cut(text, name) is not None:
                melted = True
                break
            if not header_done:
                done.set(); spinner.join()
                print(f"\r{' ' * 48}\r{HER_COLOR}{name}{RESET}: ", end="", flush=True)
                header_done = True
            print(f"{HER_COLOR}{piece}{RESET}", end="", flush=True)
            shown.append(piece)
            if voice:
                voice.feed("".join(shown))

        if not done.is_set():
            done.set(); spinner.join()
            print(f"\r{' ' * 48}\r", end="", flush=True)

        if not tripped and not looped:
            melt_cut = _foreign_speaker_cut("".join(buf), name)
            melt_kind = "chat_screenplay"
            if melt_cut is None:
                melt_cut = _prose_partner_cut("".join(buf), own_name=name)
                melt_kind = "chat_prose_melt"
            if melt_cut is not None:
                prefix = _trim_to_sentence("".join(buf)[:melt_cut].rstrip()).strip() if melt_cut > 0 else ""
                if len(prefix) >= MELT_MIN_KEEP \
                        and (not PRECISE_REGISTER or melt_kind == "chat_prose_melt"):
                    if header_done:
                        _erase_live("".join(shown))
                    _reveal(name, prefix)
                    quarantine_blocked(conn, peep_id, "".join(buf)[melt_cut:], melt_kind, "chat")
                    if voice:
                        voice.reset(); voice.finish(prefix)
                    return prefix
                looped = True

        if not tripped and not looped and _is_repetitive("".join(buf).strip(), recent_replies):
            looped = True

        if not tripped and not looped:
            reply = "".join(buf).strip()
            landed = _trim_to_sentence(reply) if finish_reason == "length" else reply
            if header_done:
                if landed != reply:
                    _erase_live("".join(shown))
                    print(f"{HER_COLOR}{name}{RESET}: {HER_COLOR}{landed}{RESET}")
                else:
                    print()
            if voice:
                voice.finish(landed if landed != reply else "".join(shown))
            return landed

        if header_done:
            _erase_live("".join(shown))
        tag = "chat_rails" if railed else ("chat_loop" if looped else "chat_reroll")
        quarantine_blocked(conn, peep_id, "".join(buf), f"{tag}_{attempt}", "chat")
        if looped and loop_prompt:
            prompt, loop_prompt = loop_prompt, None

    print(f"{HER_COLOR}{name}{RESET}: {ara_ghost.SOFT_FALLBACK}")
    if voice:
        voice.reset()
        voice.finish(ara_ghost.SOFT_FALLBACK)
    return ara_ghost.SOFT_FALLBACK


def _reveal(name, text):
    print(f"{HER_COLOR}{name}{RESET}: ", end="", flush=True)
    for ch in text:
        print(f"{HER_COLOR}{ch}{RESET}", end="", flush=True)
        if REVEAL_DELAY:
            time.sleep(REVEAL_DELAY)
    print()


_LOCK_PATH = None


def _pid_alive_windows(pid):
    import ctypes
    k32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION, STILL_ACTIVE, ERROR_ACCESS_DENIED = 0x1000, 259, 5
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not h:
        return k32.GetLastError() == ERROR_ACCESS_DENIED
    try:
        code = ctypes.c_ulong()
        if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
            return True
        return code.value == STILL_ACTIVE
    finally:
        k32.CloseHandle(h)


def _pid_alive(pid):
    if sys.platform.startswith("win"):
        return _pid_alive_windows(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _release_single_instance_lock():
    global _LOCK_PATH
    if _LOCK_PATH and os.path.exists(_LOCK_PATH):
        try:
            with open(_LOCK_PATH) as f:
                holder = int((f.read().strip() or "0"))
            if holder == os.getpid():
                os.remove(_LOCK_PATH)
        except (ValueError, OSError):
            pass
    _LOCK_PATH = None


def _fold_flag_path(conn):
    try:
        row = conn.execute("PRAGMA database_list").fetchone()
        db_path = row[2] if row else ""
        if not db_path or db_path == ":memory:":
            return None
        return db_path + ".folding"
    except Exception:
        return None


def _mark_folding(conn):
    p = _fold_flag_path(conn)
    if not p:
        return None
    try:
        with open(p, "w") as f:
            f.write(str(os.getpid()))
    except OSError:
        return None
    return p


def _clear_folding(path):
    if path:
        try:
            os.remove(path)
        except OSError:
            pass


def _acquire_single_instance_lock(conn):
    global _LOCK_PATH
    try:
        row = conn.execute("PRAGMA database_list").fetchone()
        db_path = row[2] if row else ""
        if not db_path or db_path == ":memory:":
            return True
        lock_path = db_path + ".lock"
        if os.path.exists(lock_path):
            try:
                with open(lock_path) as f:
                    other = int((f.read().strip() or "0"))
            except (ValueError, OSError):
                other = 0
            if other and other != os.getpid() and _pid_alive(other):
                holder_folding = False
                try:
                    with open(db_path + ".folding") as f:
                        holder_folding = (int((f.read().strip() or "0")) == other)
                except (ValueError, OSError):
                    holder_folding = False
                if holder_folding:
                    print(f"{BOLD}She's folding her memories right now (pid {other}).{RESET}")
                    print(f"{DIM}This runs at the end of a session and takes a few minutes — she goes quiet "
                          f"while it finishes, then exits on her own. Let it complete; do NOT kill her "
                          f"mid-fold (the one operation that can hurt a memory). Just wake her again shortly.{RESET}")
                else:
                    print(f"{BOLD}Another session is already running (pid {other}).{RESET}")
                    print(f"{DIM}Only one model fits in the Deck's RAM at a time. End that one with 'goodbye', "
                          f"or from any terminal:  kill -TERM {other}   (a clean 'goodbye' — she saves + "
                          f"writes her diary). Only if truly wedged:  kill -9 {other} ; rm {lock_path}{RESET}")
                return False
        with open(lock_path, "w") as f:
            f.write(str(os.getpid()))
        _LOCK_PATH = lock_path
        try:
            os.remove(db_path + ".folding")
        except OSError:
            pass
        atexit.register(_release_single_instance_lock)
        return True
    except Exception:
        return True


def run_chat(conn, peep_id, history_path=DEFAULT_HISTORY, show_tokens=False, model=None):
    if not _acquire_single_instance_lock(conn):
        return

    peep, permanent = load_peep(conn, peep_id)
    name = peep["name"]

    promoted = promote_staged_folds(conn, peep_id)
    if promoted:
        peep, permanent = load_peep(conn, peep_id)
        print(f"{DIM}[fold staging: {promoted} reviewed memories entered {name}'s permanent block]{RESET}")
    pending_staged = list_staged_folds(conn, peep_id)
    if pending_staged:
        print(f"{DIM}[fold staging: {len(pending_staged)} folded memories waiting in review — "
              f"/fold to read them, /fold veto <id> to refuse one]{RESET}")

    history = load_history(history_path)
    turns_this_session = 0
    session_source_ids = []
    session_start = int(time.time())
    last_user, last_response = "", ""
    _recent_injected = []
    if history:
        print(f"\n{BOLD}--- Continuing with {name} ({len(history) // 2} turns from last time) ---{RESET}")
    else:
        print(f"\n{BOLD}--- Talking with {name} ---{RESET}")
    print(f"{DIM}(Type 'quit', 'exit', or 'goodbye' to end · /help for keepsake + diary commands · "
          f"blank ⏎ = her voice on/off){RESET}\n")

    voice_streamer = ara_voice.SentenceStreamer() if VOICE else None

    while True:
        try:
            if VOICE:
                user_input = ""
                heard = ara_voice.listen()
                if heard:
                    print(f"{USER}You{RESET} (spoken): {heard}")
                    user_input = heard
                else:
                    user_input = input(f"{USER}You{RESET} {DIM}(type · blank ⏎ = voice off){RESET}: ").strip()
                    if not user_input:
                        voice_toggle()
                        continue
            else:
                user_input = input(f"{USER}You{RESET}: ").strip()
                if not user_input:
                    if voice_toggle() and VOICE and voice_streamer is None and ara_voice:
                        voice_streamer = ara_voice.SentenceStreamer()
                    continue
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if user_input.lower().strip(" .!?,") in ("quit", "exit", "goodbye", "good bye"):
            break
        if not user_input:
            continue

        if user_input.startswith("/"):
            _run_command(conn, peep_id, user_input, name,
                         last_user, last_response, history, model, history_path)
            continue

        if SAFETY_RAILS and veil_rails.blocks_input(user_input):
            print(f"{HER_COLOR}{name}{RESET}: {ara_ghost.SOFT_FALLBACK}")
            continue

        her_prefix = name + " said:"
        recent_replies = [l[len(her_prefix):].strip() for l in history if l.startswith(her_prefix)][-LOOP_LOOKBACK:]
        recent_texts = []
        for l in history[-ECHO_GUARD_LINES:]:
            if l.startswith("The user said:"):
                recent_texts.append(l[len("The user said:"):].strip())
            elif l.startswith(her_prefix):
                recent_texts.append(l[len(her_prefix):].strip())

        cooled = list(recent_texts)
        for batch in _recent_injected[:INJECT_COOLDOWN_TURNS]:
            cooled.extend(batch)
        retrieved = retrieve(conn, peep_id, user_input, limit=RETRIEVAL_LIMIT, exclude_texts=cooled,
                             exclude_user_rows_since=session_start)
        _recent_injected.insert(0, [(r["content"] or "") for r in retrieved])
        del _recent_injected[8:]

        equipped = list_equipped_keepsakes(conn, peep_id)

        system = build_chat_system(peep, permanent, equipped=equipped)
        turns  = build_chat_turns(name, user_input, history, retrieved, system=system, n_ctx=N_CTX)
        prompt = render_chat_turns(system, turns, prefill=CHAT_ASSISTANT_PREFILL)

        if show_tokens:
            tok = _estimate_tokens(prompt)
            print(f"{DIM}[prompt ~{tok} tokens | history {len(history)//2} turns]{RESET}")

        response = generate_guarded(conn, peep_id, prompt, NUM_PREDICT, name, model=model,
                                    recent_replies=recent_replies,
                                    voice=(voice_streamer if VOICE else None),
                                    loop_prompt=bare_prompt(system, turns, CHAT_ASSISTANT_PREFILL))

        if not response:
            print(f"{DIM}[{name} is quiet.]{RESET}")
            continue

        history.append(f"The user said: {user_input}")
        history.append(f"{name} said: {response}")
        trim_history(history)

        uid = save_memory(
            conn, peep_id,
            f"The user said: {user_input}",
            keywords=extract_keywords(user_input),
            importance=4,
        )
        rid = save_memory(
            conn, peep_id,
            f"I said: {response}",
            keywords=extract_keywords(response),
            importance=3,
        )
        session_source_ids.extend(i for i in (uid, rid) if i)
        turns_this_session += 1
        last_user, last_response = user_input, response

        save_history(history_path, history)

    save_history(history_path, history)
    if voice_streamer:
        voice_streamer.close()
    print(f"\n{DIM}--- Session ended — history saved ---{RESET}")

    if turns_this_session > 0:
        write_diary(conn, peep_id, history, model=model, source_ids=session_source_ids)

    if AUTO_FOLD:
        run_compression(conn, peep_id, model=model)
    else:
        print(f"{DIM}--- fold is OFF — {name}'s memories stay whole "
              f"(turn on with --fold once she's settled) ---{RESET}")


def main():
    global MODEL_PATH, CARD_PATH, AUTO_FOLD

    parser = argparse.ArgumentParser(
        description="veil_spine.py — the Veil engine (in-process GGUF companion engine)."
    )
    parser.add_argument(
        "--snapshot", metavar="JSON",
        help="Snapshot JSON to seed the DB (run once on first use).",
    )
    parser.add_argument(
        "--db", default=DEFAULT_DB, metavar="PATH",
        help=f"SQLite DB path — her memory (default: {DEFAULT_DB}).",
    )
    parser.add_argument(
        "--history", default=DEFAULT_HISTORY, metavar="PATH",
        help=f"Conversation history file (default: {DEFAULT_HISTORY}).",
    )
    parser.add_argument(
        "--model", default=None, metavar="PATH",
        help=f"Path to the GGUF weights — the swappable brain (default: {MODEL_PATH}).",
    )
    parser.add_argument(
        "--card", default=None, metavar="PATH",
        help=f"Path to her character card → the system channel (default: {CARD_PATH}).",
    )
    parser.add_argument(
        "--show-tokens", action="store_true",
        help="Print token budget info before each response.",
    )
    parser.add_argument(
        "--fold", action="store_true",
        help="Enable auto-fold (archive-first compression) at session end. OFF by default "
             "for the newborn wake — only turn on once she's settled.",
    )
    parser.add_argument(
        "--compress", action="store_true",
        help="Run compression now (regardless of threshold) then exit.",
    )
    parser.add_argument(
        "--diary", action="store_true",
        help="Read her past diary entries (newest first) then exit.",
    )
    parser.add_argument(
        "--keepsakes", action="store_true",
        help="List her keepsakes (★ = carried) then exit.",
    )
    parser.add_argument(
        "--export", metavar="OUT",
        help="Write a v3 snapshot (the FULL person: archive, folds+anchors, shelf, seed floor) "
             "to OUT then exit.",
    )
    parser.add_argument(
        "--dump-prompt", metavar="OUT",
        help="Build the prompt for a sample message and save it to OUT. No inference runs.",
    )
    args = parser.parse_args()

    if args.model:
        MODEL_PATH = os.path.expanduser(args.model)
    if args.card:
        CARD_PATH = os.path.expanduser(args.card)
    if args.fold:
        AUTO_FOLD = True

    conn = open_db(args.db)

    if args.snapshot:
        if not os.path.isfile(args.snapshot):
            print(f"Error: snapshot not found: {args.snapshot}", file=sys.stderr)
            sys.exit(1)
        import_snapshot(conn, args.snapshot)

    try:
        peep_id = find_active_peep(conn)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.compress:
        run_compression(conn, peep_id, model=args.model, force=True)
        conn.close()
        return

    if args.diary:
        read_diary(conn, peep_id)
        conn.close()
        return

    if args.keepsakes:
        _print_keepsakes(conn, peep_id)
        conn.close()
        return

    if args.export:
        snap = export_snapshot(conn, peep_id)
        with open(args.export, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent="\t")
        print(f"Snapshot written to {args.export} "
              f"({len(snap['diary'])} diary, {len(snap['keepsakes'])} keepsakes).")
        conn.close()
        return

    if args.dump_prompt:
        peep, permanent = load_peep(conn, peep_id)
        retrieved = retrieve(conn, peep_id, "hello", limit=RETRIEVAL_LIMIT)
        equipped  = list_equipped_keepsakes(conn, peep_id)
        system = build_chat_system(peep, permanent, equipped=equipped)
        turns  = build_chat_turns(peep["name"], "hello", [], retrieved, system=system, n_ctx=N_CTX)
        prompt = render_chat_turns(system, turns, prefill=CHAT_ASSISTANT_PREFILL)
        with open(args.dump_prompt, "w", encoding="utf-8") as f:
            f.write(prompt)
        print(f"Prompt written to {args.dump_prompt} (~{_estimate_tokens(prompt)} tokens, "
              f"no inference ran). System/card = {len(system)} chars.")
        conn.close()
        return

    run_chat(conn, peep_id, history_path=args.history,
             show_tokens=args.show_tokens, model=args.model)
    conn.close()


if __name__ == "__main__":
    main()
