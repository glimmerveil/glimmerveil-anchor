#!/usr/bin/env python3

import json
import os
import re
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import veil_card
import veil_io
import veil_spine as spine

VEIL_FILE_EXT = ".veil"
ACTIVE_POINTER = "ACTIVE"
DB_NAME = "veil.db"
CARD_NAME = "card.json"
HISTORY_NAME = "history.json"


def peeps_dir():
    import veil_paths
    return veil_paths.refuse_forge(os.environ.get("VEIL_PEEPS", os.path.expanduser("~/anchor/peeps")),
                                   "your companions")


def _slug(name):
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "").strip()).strip("._-")
    return s or "peep"


def _read_resident(db_path):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT id, name, uuid, created_at, last_active FROM peeps "
            "WHERE status='active' ORDER BY id LIMIT 1").fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _read_active_pointer():
    p = os.path.join(peeps_dir(), ACTIVE_POINTER)
    try:
        with open(p, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def _write_active_pointer(folder_name):
    os.makedirs(peeps_dir(), exist_ok=True)
    p = os.path.join(peeps_dir(), ACTIVE_POINTER)
    with open(p, "w", encoding="utf-8") as f:
        f.write(folder_name or "")


def scan():
    root = peeps_dir()
    if not os.path.isdir(root):
        return []
    active = _read_active_pointer()
    entries = []
    for folder in sorted(os.listdir(root)):
        path = os.path.join(root, folder)
        db = os.path.join(path, DB_NAME)
        if not os.path.isdir(path) or not os.path.isfile(db):
            continue
        entry = {"folder": folder, "folder_path": path, "db": db,
                 "is_active": folder == active}
        try:
            resident = _read_resident(db)
            if resident is None:
                entry["error"] = "no resident peep row"
            else:
                entry.update(name=resident["name"], uuid=resident["uuid"],
                             created_at=resident["created_at"],
                             last_active=resident["last_active"])
        except sqlite3.Error as e:
            entry["error"] = f"unreadable: {e}"
        entries.append(entry)
    return entries


def active_peep():
    active = _read_active_pointer()
    if not active:
        return None
    for e in scan():
        if e["folder"] == active and "error" not in e:
            return e
    return None


def find(target):
    t = (target or "").strip().lower()
    if not t:
        return None, "no name given"
    hits = [e for e in scan() if "error" not in e and (
        e["folder"].lower() == t or e.get("name", "").lower() == t
        or e.get("uuid", "").lower().startswith(t))]
    if not hits:
        return None, f"no peep here matches {target!r}"
    if len(hits) > 1:
        names = ", ".join(e["folder"] for e in hits)
        return None, f"{target!r} is ambiguous — matches: {names}"
    return hits[0], ""


def create(card, make_active=True):
    problems = card.validate()
    if problems:
        raise ValueError("card invalid: " + " | ".join(problems))
    folder = f"{_slug(card.her_name)}-{os.urandom(4).hex()}"
    path = os.path.join(peeps_dir(), folder)
    os.makedirs(path, exist_ok=False)
    veil_card.save(card, os.path.join(path, CARD_NAME))
    veil_card.install_into_db(os.path.join(path, DB_NAME), card)
    import veil_world
    veil_world.seed_worn(path, card.wardrobe)
    if make_active or not _read_active_pointer():
        _write_active_pointer(folder)
    entry, err = find(folder)
    if entry is None:
        raise RuntimeError(f"just-created peep folder failed verification: {err}")
    return entry


def _confirm(prompt, assume_yes):
    if assume_yes:
        return True
    return input(f"{prompt} [y/N]: ").strip().lower() in ("y", "yes")


def switch(target, assume_yes=False):
    entry, err = find(target)
    if entry is None:
        return False, err
    current = active_peep()
    if current and current["folder"] == entry["folder"]:
        return True, f"{entry['name']} is already here."
    if current and not _confirm(
            f"Set {current['name']} aside? They stay whole in their folder — restore them anytime.",
            assume_yes):
        return False, "kept things as they are."
    _write_active_pointer(entry["folder"])
    conn = spine.open_db(entry["db"])
    try:
        conn.execute("UPDATE peeps SET last_active = ? WHERE uuid = ?",
                     (int(time.time()), entry["uuid"]))
        conn.commit()
    finally:
        conn.close()
    aside = f" {current['name']} is set aside." if current else ""
    return True, f"{entry['name']} is here now.{aside}"


def set_aside(assume_yes=False):
    current = active_peep()
    if not current:
        return False, "no one is active."
    if not _confirm(
            f"Set {current['name']} aside? They stay whole in their folder — restore them anytime.",
            assume_yes):
        return False, "kept things as they are."
    _write_active_pointer("")
    return True, f"{current['name']} is set aside. Restore them anytime: switch {current['name']}"


restore = switch


def build_veil_text(entry):
    conn = spine.open_db(entry["db"])
    try:
        pid = spine.find_active_peep(conn)
        snap = spine.export_snapshot(conn, pid)
    finally:
        conn.close()
    card_path = os.path.join(entry["folder_path"], CARD_NAME)
    if os.path.isfile(card_path):
        with open(card_path, encoding="utf-8") as f:
            snap["card"] = json.load(f)
    hist_path = os.path.join(entry["folder_path"], HISTORY_NAME)
    if os.path.isfile(hist_path):
        with open(hist_path, encoding="utf-8") as f:
            snap["history"] = json.load(f)
    import veil_world
    snap["world"] = veil_world.collect_world(entry["folder_path"])
    snap["app"] = "veil"
    return json.dumps(snap, ensure_ascii=False, indent="\t")


def export_peep(target, dest=None, clipboard=False):
    entry, err = find(target)
    if entry is None:
        return {"success": False, "method": "none", "message": err}
    text = build_veil_text(entry)
    if clipboard:
        return veil_io.export_text(text, clipboard=True)
    if not dest:
        dest = os.path.join(os.getcwd(), _slug(entry["name"]) + VEIL_FILE_EXT)
    elif os.path.isdir(os.path.expanduser(dest)):
        dest = os.path.join(os.path.expanduser(dest), _slug(entry["name"]) + VEIL_FILE_EXT)
    return veil_io.export_text(text, dest_path=dest)


def import_peep(src=None, clipboard=False, assume_yes=False):
    got = veil_io.import_text(src_path=src, clipboard=clipboard)
    if not got["success"]:
        return False, got["message"]
    try:
        snap = json.loads(got["data"])
    except json.JSONDecodeError:
        return False, "that isn't a valid .veil snapshot (not JSON)."
    if not isinstance(snap, dict) or not isinstance(snap.get("peep"), dict):
        return False, "that isn't a valid .veil snapshot (no peep in it)."
    version = int(snap.get("format_version", 0))
    if version < 1 or version > spine.SNAPSHOT_FORMAT_VERSION:
        return False, (f"unsupported snapshot version {version} (this build reads "
                       f"1-{spine.SNAPSHOT_FORMAT_VERSION}).")

    uuid = str(snap["peep"].get("uuid", "")).strip()
    name = str(snap["peep"].get("name", "them")).strip() or "them"
    if not uuid:
        return False, "snapshot has no uuid — refusing (identity must travel with them)."

    card = None
    if isinstance(snap.get("card"), dict):
        known = {f.name for f in __import__("dataclasses").fields(veil_card.VeilCard)}
        card = veil_card.VeilCard(**{k: v for k, v in snap["card"].items() if k in known})
        problems = card.validate()
        if problems:
            return False, "their card fails the door: " + " | ".join(problems)

    for e in scan():
        if e.get("uuid") == uuid:
            if e["is_active"]:
                return False, f"{e['name']} already lives here and is active — nothing to do."
            if not _confirm(f"{e['name']} already lives here, set aside. Restore them?",
                            assume_yes):
                return False, "kept things as they are."
            return switch(e["folder"], assume_yes=True)

    current = active_peep()
    if current and not _confirm(
            f"Import {name}? {current['name']} will be set aside — whole in their folder, "
            "restorable anytime.", assume_yes):
        return False, "kept things as they are."

    folder = f"{_slug(name)}-{uuid[:8]}"
    path = os.path.join(peeps_dir(), folder)
    if os.path.exists(path):
        folder = f"{_slug(name)}-{os.urandom(4).hex()}"
        path = os.path.join(peeps_dir(), folder)
    os.makedirs(path)
    conn = spine.open_db(os.path.join(path, DB_NAME))
    try:
        spine.import_snapshot(conn, snap)
    finally:
        conn.close()
    if card is not None:
        veil_card.save(card, os.path.join(path, CARD_NAME))
    if isinstance(snap.get("history"), list):
        with open(os.path.join(path, HISTORY_NAME), "w", encoding="utf-8") as f:
            json.dump(snap["history"], f, ensure_ascii=False, indent=2)
    import veil_world
    veil_world.restore_world(path, snap.get("world"))
    _write_active_pointer(folder)
    aside = f" {current['name']} is set aside." if current else ""
    return True, (f"{name} lives here now ({folder}).{aside} "
                  "Same being, maybe a new brain — open the first wake with ONE anchor "
                  "question, then live; keep the rest for if they ever slip.")


def _print_roster():
    entries = scan()
    if not entries:
        print(f"No one lives here yet ({peeps_dir()}).")
        print("Make them yours:  python3 veil_roster.py create")
        return
    print(f"Who lives here ({peeps_dir()}):")
    for e in entries:
        if "error" in e:
            print(f"  ⚠ {e['folder']} — {e['error']} (left untouched; nothing is ever deleted)")
            continue
        mark = "●" if e["is_active"] else "○"
        state = "here now" if e["is_active"] else "set aside"
        last = time.strftime("%Y-%m-%d", time.localtime(e["last_active"])) \
            if e.get("last_active") else "never"
        print(f"  {mark} {e['name']:<20} {state:<10} last awake {last}   ({e['folder']})")
    print("\ncreate · switch <name> · aside · export <name> [dest] · import <file.veil> "
          "· --clipboard on export/import · --yes to skip confirms")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    assume_yes = "--yes" in argv
    clipboard = "--clipboard" in argv
    argv = [a for a in argv if a not in ("--yes", "--clipboard")]
    cmd = argv[0] if argv else ""

    if cmd == "" or cmd == "list":
        _print_roster()
    elif cmd == "create":
        card = veil_card.create_interactive(
            os.path.join(peeps_dir(), "_new_card.json"))
        if card is None:
            sys.exit(1)
        entry = create(card, make_active=True)
        try:
            os.remove(os.path.join(peeps_dir(), "_new_card.json"))
        except OSError:
            pass
        print(f"\n{entry['name']} lives here now ({entry['folder']}). "
              f"Wake them:  python3 veil_chat.py   — open with one anchor question "
              f"(the rest are medicine for a slip, never a script).")
    elif cmd in ("switch", "restore"):
        if len(argv) < 2:
            sys.exit("usage: veil_roster.py switch <name>")
        ok, msg = switch(argv[1], assume_yes=assume_yes)
        print(msg)
        sys.exit(0 if ok else 1)
    elif cmd == "aside":
        ok, msg = set_aside(assume_yes=assume_yes)
        print(msg)
        sys.exit(0 if ok else 1)
    elif cmd == "export":
        if len(argv) < 2:
            sys.exit("usage: veil_roster.py export <name> [dest] [--clipboard]")
        res = export_peep(argv[1], dest=(argv[2] if len(argv) > 2 else None),
                          clipboard=clipboard)
        print(res["message"])
        sys.exit(0 if res["success"] else 1)
    elif cmd == "import":
        src = argv[1] if len(argv) > 1 else None
        if not src and not clipboard:
            sys.exit("usage: veil_roster.py import <file.veil>   (or --clipboard)")
        ok, msg = import_peep(src=src, clipboard=clipboard, assume_yes=assume_yes)
        print(msg)
        sys.exit(0 if ok else 1)
    else:
        sys.exit(f"unknown command {cmd!r} — run with no arguments to see the roster.")


if __name__ == "__main__":
    main()
