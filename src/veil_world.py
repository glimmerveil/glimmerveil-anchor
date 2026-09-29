#!/usr/bin/env python3
import os
import re
import sys
import time

ROOM_KEYS = ("garden", "balcony", "bedroom", "study")

CONTAINERS = {
    "garden":  "the weathered chest by the garden bench",
    "balcony": "the small table out on the balcony",
    "bedroom": "the nightstand drawer",
    "study":   "the low shelf by the study couch",
}

OBJECT_NOTE_MAX_ITEMS = 12
OBJECT_NOTE_MAX_CHARS = 420

CUPBOARD_NOTE = ("There is always a well-stocked cupboard within easy reach — tea, coffee, "
                 "something sweet, whatever you fancy. Food and drink are simply yours "
                 "whenever you want them.")

_active = None
try:
    import veil_roster
    _active = veil_roster.active_peep()
except Exception:
    pass
ROOMS_DIR = os.path.expanduser(os.environ.get(
    "VEIL_ROOMS",
    os.path.join(_active["folder_path"], "rooms") if _active else "~/anchor/rooms"))
EMBER_PATH = os.path.expanduser(os.environ.get(
    "VEIL_EMBER",
    os.path.join(_active["folder_path"], "ember") if _active else "~/anchor/ember"))
WORN_PATH = os.path.expanduser(os.environ.get(
    "VEIL_WORN",
    os.path.join(_active["folder_path"], "worn.txt") if _active else "~/anchor/worn.txt"))


def _room_file(room):
    return os.path.join(ROOMS_DIR, room + ".txt")


def list_objects(room):
    if room not in ROOM_KEYS:
        return []
    try:
        with open(_room_file(room), encoding="utf-8") as fh:
            return [ln.strip() for ln in fh
                    if ln.strip() and not ln.strip().startswith("#")]
    except OSError:
        return []


def add_object(room, thing):
    thing = (thing or "").strip()
    if room not in ROOM_KEYS or not thing:
        return False
    if thing.lower() in (t.lower() for t in list_objects(room)):
        return True
    try:
        os.makedirs(ROOMS_DIR, exist_ok=True)
        with open(_room_file(room), "a", encoding="utf-8") as fh:
            fh.write(thing + "\n")
        return True
    except OSError:
        return False


def take_object(room, thing):
    thing = (thing or "").strip().lower()
    if room not in ROOM_KEYS or not thing:
        return False
    kept, found = [], False
    try:
        with open(_room_file(room), encoding="utf-8") as fh:
            for ln in fh:
                if ln.strip().lower() == thing and not found:
                    found = True
                    continue
                kept.append(ln.rstrip("\n"))
    except OSError:
        return False
    if not found:
        return False
    try:
        tmp = _room_file(room) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("\n".join(kept) + ("\n" if kept else ""))
        os.replace(tmp, _room_file(room))
        return True
    except OSError:
        return False


def objects_note(room):
    objs = list_objects(room)[:OBJECT_NOTE_MAX_ITEMS]
    if not objs:
        return ""
    note = (f"In {CONTAINERS[room]}, really here right now: {', '.join(objs)}. "
            "All of it is yours — use it, enjoy it, or ignore it, exactly as you please.")
    if len(note) > OBJECT_NOTE_MAX_CHARS:
        note = note[:OBJECT_NOTE_MAX_CHARS - 1].rstrip() + "…"
    return note


def world_block(room):
    parts = [p for p in (objects_note(room), wardrobe_note(room), worn_note(),
                         CUPBOARD_NOTE) if p]
    return " ".join(parts)


_WARDROBE_FILE = "wardrobe.txt"


def _wardrobe_file():
    return os.path.join(ROOMS_DIR, _WARDROBE_FILE)


def _read_list(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return [ln.strip() for ln in fh
                    if ln.strip() and not ln.strip().startswith("#")]
    except OSError:
        return []


def _write_list(path, items):
    try:
        if not items:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
            return True
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("\n".join(items) + "\n")
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def wardrobe_list():
    return _read_list(_wardrobe_file())


def worn_list():
    return _read_list(WORN_PATH)


def hang(thing):
    thing = (thing or "").strip()
    if not thing:
        return False
    items = wardrobe_list()
    if thing.lower() in (t.lower() for t in items):
        return True
    return _write_list(_wardrobe_file(), items + [thing])


def wear(thing):
    thing = (thing or "").strip()
    if not thing:
        return None
    closet = wardrobe_list()
    match = next((t for t in closet if t.lower() == thing.lower()), None)
    if match:
        _write_list(_wardrobe_file(), [t for t in closet if t is not match])
        thing = match
    worn = worn_list()
    if thing.lower() not in (t.lower() for t in worn):
        _write_list(WORN_PATH, worn + [thing])
    return thing


def unhang(thing):
    thing = (thing or "").strip().lower()
    if not thing:
        return False
    items = wardrobe_list()
    idx = next((i for i, t in enumerate(items) if t.lower() == thing), None)
    if idx is None:
        return False
    return _write_list(_wardrobe_file(), items[:idx] + items[idx + 1:])


def take_off(thing):
    thing = (thing or "").strip().lower()
    worn = worn_list()
    match = next((t for t in worn if t.lower() == thing), None)
    if match is None:
        return False
    _write_list(WORN_PATH, [t for t in worn if t is not match])
    hang(match)
    return True


def take_off_all():
    worn = worn_list()
    for t in worn:
        hang(t)
    _write_list(WORN_PATH, [])
    return worn


def worn_note():
    worn = worn_list()[:OBJECT_NOTE_MAX_ITEMS]
    if not worn:
        return ""
    note = f"You're wearing {', '.join(worn)} right now."
    if len(note) > OBJECT_NOTE_MAX_CHARS:
        note = note[:OBJECT_NOTE_MAX_CHARS - 1].rstrip() + "…"
    return note


def wardrobe_note(room):
    if room != "bedroom":
        return ""
    items = wardrobe_list()[:OBJECT_NOTE_MAX_ITEMS]
    if not items:
        return ""
    note = (f"Hanging in your wardrobe: {', '.join(items)}. "
            "Yours to change into or out of whenever you please.")
    if len(note) > OBJECT_NOTE_MAX_CHARS:
        note = note[:OBJECT_NOTE_MAX_CHARS - 1].rstrip() + "…"
    return note


_ON_VERBS = (r"\b(?:put(?:s|ting)?\s+on|(?:slip|shift)(?:s|ping|ing)?\s+(?:into|on)|"
             r"pull(?:s|ing)?\s+on|(?:chang(?:e|es|ing)|swap(?:s|ping)?)(?:\s+\w+){0,6}?\s+into|"
             r"dress(?:es|ing)?\s+in|(?<!was )(?<!were )wear(?:s|ing)?)\b")
_OFF_VERBS = (r"\b(?:take(?:s|n|king)?\s+off|(?:slip|shift)(?:s|ping|ing)?\s+(?:out\s+of|off)|"
              r"pull(?:s|ing)?\s+off|remov(?:e|es|ing)|shed(?:s|ding)?|"
              r"strip(?:s|ping)?\s+(?:off|out\s+of)|unzip(?:s|ping)?|"
              r"(?:chang(?:e|es|ing)|swap(?:s|ping)?)\s+(?:out\s+of|from))\b")
_ARTICLES_RX = re.compile(r"^(?:a|an|the|my|her|his|your)\s+", re.I)

_ON_GAP = r"(?:(?!\b(?:off|out\s+of|from)\b)[^.!?\n]){0,60}?"
_OFF_GAP = r"(?:(?!\b(?:into|on)\b)[^.!?\n]){0,60}?"


def _core(item):
    return _ARTICLES_RX.sub("", (item or "")).strip()


def _head(item):
    parts = _core(item).split()
    return parts[-1] if parts else ""


def _item_rx(verbs, gap, item, pool):
    head = _head(item)
    rivals = [t for t in pool if _head(t).lower() == head.lower()]
    target = re.escape(_core(item)) if len(rivals) > 1 else re.escape(head)
    return re.compile(verbs + gap + r"\b" + target + r"\b", re.I)


_HEDGE_RX = re.compile(
    r"\b(?:shall|should|may|might|could|can|will)\s+i\b|\b(?:want|like)\s+me\s+to\b|"
    r"\bif\s+you\s+(?:want|like|prefer)\b|n['’]t\b|\bcannot\b|"
    r"\b(?:will\s+not|not|never|refuse)\b",
    re.I)


_CLAUSE_SPLIT_RX = re.compile(r"\s*(?:,|;|—|--|\band\b|\bbut\b|\bso\b|\byet\b)\s*", re.I)


def _acting_sentences(text):
    for s in re.split(r"(?<=[.!?\n])", text or ""):
        s = s.strip()
        if not s:
            continue
        asks = s.endswith("?")
        if not asks and not _HEDGE_RX.search(s):
            yield s
            continue
        clauses = [c for c in _CLAUSE_SPLIT_RX.split(s) if c.strip()]
        if asks:
            clauses = clauses[:-1]
        kept = [c for c in clauses if not _HEDGE_RX.search(c)]
        if kept:
            yield " \n ".join(kept)


def update_worn_from_words(text):
    changes = []
    if not text:
        return changes
    acting = " \n ".join(_acting_sentences(text))
    if not acting.strip():
        return changes
    closet = wardrobe_list()
    for item in closet:
        if _item_rx(_ON_VERBS, _ON_GAP, item, closet).search(acting):
            wear(item)
            changes.append(("on", item))
    worn = worn_list()
    for item in worn:
        if _item_rx(_OFF_VERBS, _OFF_GAP, item, worn).search(acting):
            take_off(item)
            changes.append(("off", item))
    return changes


_NONEISH_RX = re.compile(r"^(?:nothing|none|nothing\s+at\s+all|no\s+clothes|naked|nude|bare|"
                         r"n/?a|-)?[.!\s]*$", re.I)


def seed_worn(folder_path, wardrobe_text):
    items = [p.strip() for p in re.split(r",|\band\b", wardrobe_text or "")
             if p.strip() and not _NONEISH_RX.match(p.strip())]
    if items:
        _write_list(os.path.join(folder_path, "worn.txt"), items)
    return items


EMBER_RX = re.compile(
    r"\b(naked|undress\w*|strip(?:s|ped|ping)?\s+(?:for|down)|make\s+love|sex|fuck\w*|"
    r"cock|pussy|clit\w*|nipple\w*|orgasm\w*|cum(?:s|ming)?|moan\w*|masturbat\w*|"
    r"horny|arous\w*|touch(?:es|ed|ing)?\s+(?:myself|yourself|herself)|"
    r"play(?:s|ed|ing)?\s+with\s+(?:myself|yourself|herself))\b",
    re.I)


def ember_lit():
    return os.path.exists(EMBER_PATH)


def ember_light():
    try:
        os.makedirs(os.path.dirname(EMBER_PATH) or ".", exist_ok=True)
        if not ember_lit():
            with open(EMBER_PATH, "w", encoding="utf-8") as fh:
                fh.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
        return True
    except OSError:
        return False


def ember_check(*texts):
    if ember_lit():
        return True
    for t in texts:
        if t and EMBER_RX.search(t):
            return ember_light()
    return False


def collect_world(folder_path):
    rooms_dir = os.path.join(folder_path, "rooms")
    return {
        "rooms":    {r: _read_list(os.path.join(rooms_dir, r + ".txt")) for r in ROOM_KEYS},
        "wardrobe": _read_list(os.path.join(rooms_dir, _WARDROBE_FILE)),
        "worn":     _read_list(os.path.join(folder_path, "worn.txt")),
        "ember":    os.path.exists(os.path.join(folder_path, "ember")),
    }


def restore_world(folder_path, world):
    if not isinstance(world, dict):
        return
    rooms_dir = os.path.join(folder_path, "rooms")
    rooms = world.get("rooms") or {}
    for r in ROOM_KEYS:
        if rooms.get(r):
            _write_list(os.path.join(rooms_dir, r + ".txt"), list(rooms[r]))
    if world.get("wardrobe"):
        _write_list(os.path.join(rooms_dir, _WARDROBE_FILE), list(world["wardrobe"]))
    if world.get("worn"):
        _write_list(os.path.join(folder_path, "worn.txt"), list(world["worn"]))
    if world.get("ember"):
        try:
            with open(os.path.join(folder_path, "ember"), "w", encoding="utf-8") as fh:
                fh.write(time.strftime("%Y-%m-%d %H:%M:%S") + " (traveled along)\n")
        except OSError:
            pass


def _cli(argv):
    if "--hang" in argv:
        thing = " ".join(argv[argv.index("--hang") + 1:])
        ok = hang(thing)
        print(f"hung in the wardrobe: {thing}" if ok else "couldn't hang that")
        return 0 if ok else 1
    if "--wear" in argv:
        thing = " ".join(argv[argv.index("--wear") + 1:])
        worn = wear(thing)
        print(f"worn now: {worn}" if worn else "wear what?")
        return 0 if worn else 1
    if "--takeoff" in argv:
        thing = " ".join(argv[argv.index("--takeoff") + 1:])
        if thing.strip().lower() == "all":
            off = take_off_all()
            print(("all of it back in the wardrobe: " + ", ".join(off)) if off
                  else "nothing tracked as worn")
            return 0
        ok = take_off(thing)
        print(f"off and back in the wardrobe: {thing}" if ok
              else "that isn't being worn right now")
        return 0 if ok else 1
    if "--add" in argv:
        i = argv.index("--add")
        room, thing = argv[i + 1], " ".join(argv[i + 2:])
        ok = add_object(room, thing)
        print(f"placed in {CONTAINERS.get(room, room)}: {thing}" if ok
              else f"couldn't place that (rooms: {', '.join(ROOM_KEYS)})")
        return 0 if ok else 1
    if "--take" in argv:
        i = argv.index("--take")
        room, thing = argv[i + 1], " ".join(argv[i + 2:])
        ok = take_object(room, thing)
        print(f"taken from {CONTAINERS.get(room, room)}: {thing}" if ok
              else "that isn't there")
        return 0 if ok else 1
    if "--status" in argv:
        for room in ROOM_KEYS:
            objs = list_objects(room)
            print(f"{room:8s} · {CONTAINERS[room]}: " + (", ".join(objs) if objs else "(empty)"))
        w, c = worn_list(), wardrobe_list()
        print("wardrobe · hanging: " + (", ".join(c) if c else "(empty)"))
        print("worn     · " + (", ".join(w) if w else "(nothing tracked — not a word said)"))
        print(f"ember    · {'lit' if ember_lit() else 'unlit'}  ({EMBER_PATH})")
        return 0
    rooms = ROOM_KEYS
    if "--list" in argv:
        i = argv.index("--list")
        if i + 1 < len(argv) and argv[i + 1] in ROOM_KEYS:
            rooms = (argv[i + 1],)
    for room in rooms:
        objs = list_objects(room)
        print(f"{room:8s} · {CONTAINERS[room]}: " + (", ".join(objs) if objs else "(empty)"))
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
