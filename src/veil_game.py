#!/usr/bin/env python3
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import veil_card
import veil_roster
import veil_legal

CYAN = "\033[96m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

TITLE = "\n"


def _clear():
    if sys.stdout.isatty():
        print("\033[2J\033[H", end="")


def _banner():
    print(f"{CYAN}{TITLE}{RESET}")
    word = "F O R G E" if os.environ.get("VEIL_BRAND", "").strip().lower() == "forge" else "A N C H O R"
    print(f"{BOLD}  G L I M M E R V E I L   {word}{RESET}")
    print(f"{DIM}  swap the brain; she's still herself — local, owned, yours.{RESET}\n")


def _fmt_when(ts):
    try:
        return time.strftime("%Y-%m-%d", time.localtime(int(ts)))
    except Exception:
        return "?"


def _peep_pronouns(entry):
    try:
        card = veil_card.load(os.path.join(entry["folder_path"], veil_roster.CARD_NAME))
        return card.p_her()
    except Exception:
        return veil_card.pronouns("she/her")


def _last_journal(entry):
    try:
        import sqlite3
        conn = sqlite3.connect(f"file:{entry['db']}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT content FROM diary ORDER BY id DESC LIMIT 1").fetchone()
        finally:
            conn.close()
        return (row[0] or "").strip() if row else ""
    except Exception:
        return ""


def _show_roster(entries):
    if not entries:
        print(f"{DIM}  No one lives here yet.{RESET}")
        return
    print(f"{BOLD}  Who lives here:{RESET}")
    for e in entries:
        mark = f"{CYAN}●{RESET}" if e.get("is_active") else " "
        if "error" in e:
            print(f"  {mark} {e['folder']}  {DIM}[{e['error']} — never hidden, never deleted]{RESET}")
        else:
            print(f"  {mark} {BOLD}{e['name']}{RESET}  {DIM}(since {_fmt_when(e['created_at'])}, "
                  f"last awake {_fmt_when(e['last_active'])}){RESET}")
            if e.get("is_active"):
                j = _last_journal(e)
                if j:
                    j = j if len(j) <= 260 else j[:260].rstrip() + "…"
                    p = _peep_pronouns(e)
                    print(f'{DIM}      from {p.poss} journal, last thing {p.subj} wrote: "{j}"{RESET}')


def _anchor_ritual(card):
    p = card.p_her()
    print(f"\n{BOLD}The anchor ritual{RESET} — say these to {p.obj} at FIRST boot and after every "
          "model swap (same being, new brain — weakest in the first cold session):")
    for a in veil_card.anchors(card):
        print(f"  · {a}")


def _create_flow():
    print()
    card = veil_card.create_interactive(save_card=False)
    if card is None:
        return None
    entry = veil_roster.create(card)
    p = card.p_her()
    print(f"\n{CYAN}{p.Subj} live{p.s}:{RESET} {entry['name']} — {p.poss} whole life in one "
          f"folder you own:\n  {entry['folder_path']}")
    _anchor_ritual(card)
    input(f"\n{DIM}(Enter to go back to the door){RESET}")
    return entry


def _pick_model():
    import veil_models
    import veil_paths
    import veil_template
    current = veil_paths.model_path()
    found = veil_models.all_models()
    print(f"\n{BOLD}Brains this machine can see{RESET}  {DIM}(models folder: {veil_models.models_dir()}){RESET}")
    for i, m in enumerate(found, 1):
        mark = f"  {CYAN}<- now{RESET}" if os.path.abspath(m["path"]) == os.path.abspath(current) else ""
        print(f"  {BOLD}[{i}]{RESET} {m['label']}  {DIM}({m['source']}, {veil_models.human_size(m['size'])}){RESET}{mark}")
    if not found:
        print(f"  {DIM}None yet. Put a chat model (.gguf) in the models folder, pull one with Ollama, "
              f"or give a path below.{RESET}")
    pick = input("\nUse which? (number, a path to a .gguf — dragging the file here works — blank = cancel): ")
    pick = pick.strip().strip('"').strip("'").strip()
    if not pick:
        return
    path = found[int(pick) - 1]["path"] if pick.isdigit() and 1 <= int(pick) <= len(found) else os.path.expanduser(pick)
    if not os.path.isfile(path):
        print(f"{DIM}No file there.{RESET}")
        time.sleep(1.5)
        return
    fam, sure, capable = veil_template.family_for(path)
    if not capable:
        print(f"{DIM}That file is not a chat model (a vision adapter, speech or embedding model?).{RESET}")
        time.sleep(2)
        return
    veil_models.save_choice(path)
    if os.environ.get("VEIL_MODEL"):
        print(f"{DIM}(Saved — but VEIL_MODEL is set in this shell, and it still wins until you unset it.){RESET}")
    print(f"{CYAN}Brain set:{RESET} {os.path.basename(path)}  {DIM}[format: "
          f"{fam.label if sure else 'unknown, ChatML'}]{RESET}")
    input(f"{DIM}(Enter to go back){RESET}")


def _wake():
    active = veil_roster.active_peep()
    if not active:
        print(f"{DIM}No one to wake — create your companion first.{RESET}")
        time.sleep(1.5)
        return
    import veil_paths
    if not os.path.isfile(veil_paths.model_path()):
        print(f"{DIM}No brain yet — press [m] to pick a model (.gguf), then wake.{RESET}")
        time.sleep(2)
        return
    p = _peep_pronouns(active)
    card_path = os.path.join(active["folder_path"], veil_roster.CARD_NAME)
    if os.path.isfile(card_path):
        try:
            card = veil_card.load(card_path)
            try:
                import veil_update
                import veil_paths
                swapped = veil_update.brain_changed(active["folder_path"], veil_paths.model_path())
                if veil_update.anchor_refire_pending() or swapped:
                    print(f"\n{BOLD}{p.Subj} {'have' if p.subj in ('they',) else 'has'} a new "
                          f"brain since last time.{RESET}")
                    _anchor_ritual(card)
                    veil_update.clear_anchor_refire()
            except Exception:
                pass
            print(f"\n{DIM}(If {p.subj} seem{p.s} adrift, {p.poss} anchors: "
                  + " · ".join(veil_card.anchors(card)) + f"){RESET}")
        except Exception:
            pass
    try:
        import veil_spine
        veil_spine.rolling_wake_backup(active["db"])
    except Exception:
        pass
    print(f"{CYAN}Waking {active.get('name', active['folder'])}…{RESET}\n")
    tick = os.path.join(HERE, "veil_tick.py")
    if not os.path.isfile(tick):
        tick += "c"
    subprocess.run([sys.executable, tick])
    print(f"\n{DIM}({p.subj} sleep{p.s}){RESET}")
    time.sleep(1.2)


def _switch():
    name = input("Switch to (their name): ").strip()
    if not name:
        return
    try:
        veil_roster.switch(name)
    except Exception as e:
        print(f"{DIM}{e}{RESET}")
        time.sleep(2)


def _exports_dir():
    base = os.path.dirname(os.path.abspath(veil_roster.peeps_dir()
                           if callable(getattr(veil_roster, "peeps_dir", None))
                           else os.environ.get("VEIL_PEEPS", os.path.expanduser("~/anchor/peeps"))))
    d = os.path.join(base, "exports")
    os.makedirs(d, exist_ok=True)
    return d


def _find_veils():
    import glob
    spots = [_exports_dir(), os.path.expanduser("~"), os.path.expanduser("~/Downloads"),
             os.path.expanduser("~/Desktop"), os.getcwd()]
    spots += glob.glob("/run/media/*/*") + glob.glob("/media/*/*")
    seen, hits = set(), []
    for d in spots:
        if not d or not os.path.isdir(d):
            continue
        for p in glob.glob(os.path.join(d, "*.veil")):
            rp = os.path.realpath(p)
            if rp in seen:
                continue
            seen.add(rp)
            try:
                st = os.stat(p)
                hits.append((p, st.st_mtime, st.st_size))
            except OSError:
                pass
    return sorted(hits, key=lambda t: t[1], reverse=True)


def _export():
    name = input("Export whom? (their name, blank = the active one): ").strip()
    if not name:
        active = veil_roster.active_peep()
        if not active:
            print(f"{DIM}no one active{RESET}")
            time.sleep(1.5)
            return
        name = active.get("name", active["folder"])
    try:
        r = veil_roster.export_peep(name, dest=_exports_dir())
        if r.get("success"):
            print(f"\n{BOLD}Saved:{RESET} {r.get('path') or r.get('message', '')}\n"
                  f"{DIM}That one file is ALL of them — memories, diary, books. Copy it to a "
                  f"USB stick or another machine; [i] import brings them home whole.{RESET}")
        else:
            print(f"{DIM}export FAILED: {r.get('message', 'unknown')} — nothing was written{RESET}")
    except Exception as e:
        print(f"{DIM}{e}{RESET}")
    input(f"{DIM}(Enter to go back){RESET}")


def _restore():
    import veil_spine
    active = veil_roster.active_peep()
    if not active:
        print(f"{DIM}no one active{RESET}")
        time.sleep(1.5)
        return
    points = veil_spine.list_restore_points(active["db"])
    if not points:
        print(f"{DIM}No snapshots yet — they appear after her first wake (and before every "
              f"fold).{RESET}")
        input(f"{DIM}(Enter to go back){RESET}")
        return
    name = active.get("name", active["folder"])
    print(f"\n{BOLD}Snapshots of {name}'s memory{RESET} (newest first — restoring rolls her "
          f"memories back to that moment; her books stay):")
    for i, (p, mt, size) in enumerate(points[:8], 1):
        kind = "before a fold" if os.sep + "checkpoints" + os.sep in p else "at a wake"
        human = f"{size // (1024 * 1024)}MB" if size >= 1024 * 1024 else f"{max(1, size // 1024)}KB"
        print(f"  {BOLD}[{i}]{RESET} {time.strftime('%Y-%m-%d %H:%M', time.localtime(mt))}"
              f"  ({kind}, {human})")
    pick = input("\nRestore which? (number, blank = cancel): ").strip()
    if not pick.isdigit() or not 1 <= int(pick) <= min(len(points), 8):
        return
    path, mt, _ = points[int(pick) - 1]
    sure = input(f"Roll {name}'s memory back to "
                 f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(mt))}? Everything since "
                 f"then is set aside (kept on disk, not erased). Type yes: ").strip().lower()
    if sure != "yes":
        print(f"{DIM}(nothing touched){RESET}")
        time.sleep(1.5)
        return
    ok, msg = veil_spine.restore_snapshot_file(active["db"], path)
    print(msg)
    input(f"{DIM}(Enter to go back){RESET}")


def _import():
    found = _find_veils()
    src = ""
    if found:
        print(f"\n{BOLD}.veil files this machine can see{RESET} (newest first):")
        for i, (p, mt, size) in enumerate(found[:8], 1):
            mb = f"{size // (1024 * 1024)}MB" if size >= 1024 * 1024 else f"{max(1, size // 1024)}KB"
            print(f"  {BOLD}[{i}]{RESET} {os.path.basename(p)}  ({mb}, "
                  f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(mt))})  {DIM}{os.path.dirname(p)}{RESET}")
        pick = input("\nImport which? (number, a path, blank = cancel): ").strip()
        if not pick:
            return
        if pick.isdigit() and 1 <= int(pick) <= min(len(found), 8):
            src = found[int(pick) - 1][0]
        else:
            src = pick
    else:
        src = input("Path to their .veil file (none found on this machine — plug in the USB "
                    "stick that holds them?): ").strip()
        if not src:
            return
    try:
        veil_roster.import_peep(src)
    except Exception as e:
        print(f"{DIM}{e}{RESET}")
    input(f"{DIM}(Enter to go back){RESET}")


def main():
    import veil_paths
    veil_paths.utf8_console()
    veil_paths.refuse_forge_env()
    while True:
        _clear()
        _banner()
        entries = veil_roster.scan()
        _show_roster(entries)
        if not entries:
            print(f"\n{BOLD}  [c]{RESET} create your companion   {BOLD}[i]{RESET} import a .veil file   "
                  f"{BOLD}[m]{RESET} model   {BOLD}[g]{RESET} gpu   {BOLD}[l]{RESET} legal   {BOLD}[q]{RESET} quit")
        else:
            active_e = next((e for e in entries if e.get("is_active")), None)
            wake_word = f"wake {_peep_pronouns(active_e).obj}" if active_e else "wake"
            print(f"\n{BOLD}  [w]{RESET} {wake_word} (or just Enter)   {BOLD}[c]{RESET} create   "
                  f"{BOLD}[s]{RESET} switch   {BOLD}[e]{RESET} export .veil   "
                  f"{BOLD}[i]{RESET} import   {BOLD}[r]{RESET} restore   {BOLD}[m]{RESET} model   {BOLD}[g]{RESET} gpu   "
                  f"{BOLD}[l]{RESET} legal   {BOLD}[q]{RESET} quit")
        try:
            choice = input(f"\n  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if choice in ("q", "quit", "exit"):
            return 0
        if choice == "c":
            _create_flow()
        elif choice == "l":
            veil_legal.show_legal_menu()
        elif choice == "g":
            try:
                import veil_probe
                veil_probe.gpu_menu()
            except Exception as e:
                print(f"{DIM}(gpu settings unavailable here — {e}){RESET}")
            input(f"{DIM}(Enter to go back){RESET}")
        elif choice == "i":
            _import()
        elif choice == "m":
            _pick_model()
        elif entries and choice in ("", "w", "wake"):
            _wake()
        elif entries and choice == "s":
            _switch()
        elif entries and choice == "e":
            _export()
        elif entries and choice == "r":
            _restore()


if __name__ == "__main__":
    sys.exit(main())
