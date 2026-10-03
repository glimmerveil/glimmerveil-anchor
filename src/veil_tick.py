#!/usr/bin/env python3
import collections
import os
import re
import select
import signal
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import veil_chat
import veil_card
import veil_shelf as B
import veil_world as W
import veil_canary as Canary

spine = veil_chat.spine
CARD = veil_chat.CARD
import veil_grounding

HER = spine.HER_COLOR
DIM, RESET, BOLD = spine.DIM, spine.RESET, spine.BOLD

YOUR_NAME = (CARD.your_name if CARD else "your partner")
PARTNER_WORD = (CARD.partner_word if CARD else "partner")
P = (CARD.p_her() if CARD and hasattr(CARD, "p_her") else veil_card.pronouns("she/her"))
PY = (CARD.p_you() if CARD and hasattr(CARD, "p_you") else veil_card.pronouns("he/him"))

_auto_env = os.environ.get("VEIL_AUTONOMY", "")
AUTONOMY = (_auto_env == "1") if _auto_env in ("0", "1") else bool(CARD and CARD.autonomy)

LANES = ["rest", "read", "write", "drift"]
REAL_LANES = set(LANES)
MEMORABLE_LANES = {"read", "write", "indulge", "murmur", "watch"}

SLOW_TICK = float(os.environ.get("VEIL_TICK_SECONDS", "20"))
PATIENCE_SECONDS = float(os.environ.get("VEIL_PATIENCE_SECONDS", "300"))

_active = None
try:
    import veil_roster
    _active = veil_roster.active_peep()
except Exception:
    pass
NOTEBOOK_DIR = os.path.expanduser(os.environ.get(
    "VEIL_NOTEBOOK",
    os.path.join(_active["folder_path"], "notebook") if _active else "~/anchor/notebook"))

HEARTBEAT_PATH = os.path.expanduser(os.environ.get("VEIL_HEARTBEAT", "~/anchor/heartbeat"))


def _heartbeat(doing):
    try:
        os.makedirs(os.path.dirname(HEARTBEAT_PATH), exist_ok=True)
        tmp = HEARTBEAT_PATH + ".tmp"
        with open(tmp, "w") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S") + " · " + doing + "\n")
        os.replace(tmp, HEARTBEAT_PATH)
    except OSError:
        pass


LOCATIONS = {
    "manor": {
        "title": "a moonlit manor",
        "rooms": {
            "garden":  "the walled garden of the manor — roses {subj} tend{s}, soft grass, a bench under the old tree",
            "balcony": "the manor's stone balcony — night air over the balustrade, the whole sky; where {subj} stargaze{s}",
            "bedroom": "{poss} bedroom in the manor — warm, lamplit, {posspro}; the wardrobe stands here",
            "study":   "the manor's study — book-lined walls, a long couch with a low table before "
                       "it, a deep reading chair, a small writing desk",
        },
    },
    "tower": {
        "title": "an enchanted tower",
        "rooms": {
            "garden":  "the wild garden at the tower's foot — moss, night-blooming flowers, a mossy bench by the door",
            "balcony": "the tower's high balcony — above the clouds some nights, stars close enough to touch",
            "bedroom": "{poss} round bedroom high in the tower — warm, curved walls, {posspro}; the wardrobe stands here",
            "study":   "the tower's study — a spiral of shelves, a long couch with a low table, a "
                       "deep chair by the window, a small desk",
        },
    },
}
LOCATION_KEY = (CARD.location if CARD and getattr(CARD, "location", "") in LOCATIONS else "manor")
LOCATION = LOCATIONS[LOCATION_KEY]
ROOMS = {k: v.format(subj=P.subj, s=P.s, poss=P.poss, posspro=P.posspro)
         for k, v in LOCATION["rooms"].items()}
_PLACE_PEEP = None
try:
    import veil_roster as _vr
    _PLACE_PEEP = _vr.active_peep()
except Exception:
    pass
PLACE_PATH = os.path.expanduser(os.environ.get(
    "VEIL_PLACE",
    os.path.join(_PLACE_PEEP["folder_path"], "place") if _PLACE_PEEP else "~/anchor/place"))
WAKE_ROOM = "garden"


def _load_place():
    try:
        with open(PLACE_PATH, encoding="utf-8") as fh:
            saved = fh.read().strip()
        return saved if saved in ROOMS else WAKE_ROOM
    except OSError:
        return WAKE_ROOM


def _save_place(place):
    try:
        os.makedirs(os.path.dirname(PLACE_PATH), exist_ok=True)
        tmp = PLACE_PATH + ".tmp"
        with open(tmp, "w") as fh:
            fh.write(place + "\n")
        os.replace(tmp, PLACE_PATH)
    except OSError:
        pass


_WORLD = {"place": _load_place()}


def _place():
    return _WORLD["place"]


def _go_to(place):
    if place in ROOMS:
        _WORLD["place"] = place
        _save_place(place)


def _place_block(together=False):
    desc = ROOMS[_place()]
    who = (f"You and {YOUR_NAME} are here together right now." if together
           else "You are here on your own right now.")
    if not together and _NIGHT["him_asleep"]:
        spot = _NIGHT["his_spot"] or _place()
        who = (f"{YOUR_NAME} is asleep right here beside you, breathing slow — the night is "
               f"yours, and {PY.subj} {PY.be} safe." if spot == _place() else
               f"You are up on your own right now; {YOUR_NAME} is asleep in the "
               f"{spot.replace('_', ' ')}.")
    world = W.world_block(_place())
    return (f"YOUR PLACE — real, yours, where you are at this moment: {desc}. {who} "
            "Speak and act from here. Move to another room whenever you choose — just say so."
            + ((" " + world) if world else ""))


_ROOM_PHRASES = {
    "garden":  re.compile(r"\b((?:go|going|out)\s+for\s+a\s+walk|take\s+a\s+walk|"
                          r"walk\s+with\s+me)\b", re.I),
    "balcony": re.compile(r"\b(stargaz\w*|watch\s+the\s+stars|look\s+at\s+the\s+stars)\b", re.I),
    "bedroom": re.compile(r"\b(to\s+bed)\b", re.I),
}
_GO_FRAME = (r"\b(?:go|goes|going|went|gone|head|heads|heading|headed|come|comes|coming|came|"
             r"walk|walking|walked|step|stepping|stepped|move|moves|moving|moved|"
             r"carry|carries|carrying|carried|bring|brings|bringing|brought|"
             r"take|takes|taking|took|"
             r"meet|follow|show|out|into|onto|let'?s|off\s+to|back\s+to|up\s+to|down\s+to)\b"
             r"[^.!?\n]{0,50}?")
_HERE_FRAME = (r"\b(?:we'?re|we\s+are|you'?re|you\s+are|i'?m|i\s+am)\s+"
               r"(?:all\s+|both\s+)?(?:back\s+)?(?:now\s+)?(?:in|at|on|out\s+on)\s+"
               r"(?:the\s+|my\s+|your\s+|our\s+)?")
_ROOM_NOUNS = (("garden", r"garden"), ("balcony", r"balcony"),
               ("bedroom", r"bedroom|wardrobe"), ("study", r"study|library"))
_ROOM_NOUN_GO = {room: re.compile(_GO_FRAME + r"\b(?:" + nouns + r")\b", re.I)
                 for room, nouns in _ROOM_NOUNS}
_ROOM_HERE = {room: re.compile(_HERE_FRAME + r"(?:" + nouns + r")\b", re.I)
              for room, nouns in _ROOM_NOUNS}
_NO_GO_RX = re.compile(
    r"\b(?:not|never|no\s+longer|anymore|any\s+more|was|were|got|had|stuck|"
    r"remember\w*|forgot\w*|forget|yesterday|earlier|used\s+to|last\s+(?:night|time))\b"
    r"|n['’]t\b|\bcannot\b"
    r"|\boff\s+(?:the|this|that|my|your|her)\b", re.I)
_ROOM_ASSENT = re.compile(
    r"^\s*(yes|yeah|yep|sure|ok(?:ay)?|alright|of course|let'?s go|i'?d love|lead the way|"
    r"sounds\s+(?:good|nice|lovely))\b", re.I)


def _update_place_from_chat(user_input, last_her_line):
    low = user_input or ""
    hits = []
    for m in re.finditer(r"[^.!?\n]+", low):
        sent, base = m.group(), m.start()
        if _NO_GO_RX.search(sent):
            continue
        for room, rx in _ROOM_PHRASES.items():
            hits += [(base + h.start(), room) for h in rx.finditer(sent)]
        for room, rx in _ROOM_NOUN_GO.items():
            hits += [(base + h.start(), room) for h in rx.finditer(sent)]
        for room, rx in _ROOM_HERE.items():
            hits += [(base + h.start(), room) for h in rx.finditer(sent)]
    if hits:
        _go_to(max(hits)[1])
        return
    if last_her_line and _ROOM_ASSENT.match(low):
        for room in ROOMS:
            if room in last_her_line.lower():
                _go_to(room)
                return


_NIGHT = {
    "him_asleep": False,
    "his_spot": None,
    "her_sleep_until": 0.0,
    "watches": 0,
}

HER_SLEEP_SECONDS = float(os.environ.get("VEIL_SLEEP_SECONDS", "21600"))

_GOODNIGHT_CUE = re.compile(r"^\s*(?:good\s*night|night[\s-]+night|nighty[\s-]*night)\b", re.I)
_GOODNIGHT_NO = re.compile(
    r"\b(?:say|says|said|saying|didn'?t|never|forgot\w*|remember\w*|last\s+night|yesterday|"
    r"was|were|for)\b", re.I)


def _goodnight_cue(line):
    for m in re.finditer(r"[^.!?\n]+[.!?…]*", line or ""):
        sent = m.group().strip()
        if not sent or not _GOODNIGHT_CUE.match(sent):
            continue
        if "?" in sent or _GOODNIGHT_NO.search(sent):
            continue
        return True
    return False


_SLEEP_WORD = re.compile(r"\b(?:sleep|asleep|bed|rest|lie\s+down|lay\s+down|curl\s+up|doze|nap)\b", re.I)
_TOGETHER_WORD = re.compile(
    r"\b(?:together|with\s+me|beside\s+me|next\s+to\s+me|hold\s+me|in\s+my\s+arms|cuddl\w*|snuggl\w*)\b", re.I)


def _sleep_together_cue(line):
    return bool(line and _SLEEP_WORD.search(line) and _TOGETHER_WORD.search(line))


def _night_falls(spot=None):
    spot = spot if spot in ROOMS else _place()
    _NIGHT.update(him_asleep=True, his_spot=spot, watches=0)
    print(f"{DIM}[goodnight — {YOUR_NAME} sleeps in the {spot.replace('_', ' ')}; the night is "
          f"{P.posspro}, and {PY.poss} next words are the morning]{RESET}")
    _heartbeat(f"{YOUR_NAME} is asleep in the {spot} — {P.poss} night, all well")


def _morning_breaks():
    spot = _NIGHT["his_spot"]
    she_slept = _she_sleeps()
    drifted = spot and _place() != spot
    if spot:
        _go_to(spot)
    _NIGHT.update(him_asleep=False, his_spot=None, her_sleep_until=0.0)
    where = ROOMS[_place()]
    if she_slept:
        print(f"{DIM}[morning — your voice reaches {P.obj}; {P.subj} stir{P.s} awake with you in {where}]{RESET}")
    elif drifted:
        print(f"{DIM}[morning — {P.subj} come{P.s} back to you, in {where}]{RESET}")
    else:
        print(f"{DIM}[morning — {P.subj} {P.be} right here with you, in {where}]{RESET}")


def _she_sleeps():
    return _NIGHT["her_sleep_until"] > time.time()


def _wake_her():
    if _she_sleeps():
        _NIGHT["her_sleep_until"] = 0.0
        print(f"{DIM}[your voice reaches {P.obj} — {P.subj} stir{P.s} awake]{RESET}")


def _sleep_with_him():
    _NIGHT["her_sleep_until"] = time.time() + HER_SLEEP_SECONDS
    print(f"{HER}[{P.subj} curl{P.s} up close and let{P.s} sleep take {P.obj}, there with you]{RESET}")
    _heartbeat(f"asleep beside {YOUR_NAME} in the {_place()} — {P.poss} chosen rest, {PY.poss} voice wakes {P.obj}")


_VOICE_STREAMER = None


def _rails(text):
    if text and getattr(spine, "SAFETY_RAILS", False) and spine.veil_rails.blocks_output(text):
        return ""
    return text


def _speak_aloud(text):
    if _VOICE_STREAMER and text and getattr(spine, "VOICE", False):
        try:
            _VOICE_STREAMER.reset()
            _VOICE_STREAMER.finish(text)
        except Exception:
            pass


_WOKE_AT = None

_RECENT_INJECTED = collections.deque(maxlen=8)


def _daypart(hour):
    if 5 <= hour <= 11:
        return "morning"
    if 12 <= hour <= 16:
        return "afternoon"
    if 17 <= hour <= 20:
        return "evening"
    return "night"


def _humanize_elapsed(seconds):
    if seconds < 90:
        return "moments"
    if seconds < 90 * 60:
        return f"{max(1, int(seconds // 60))} minutes"
    if seconds < 36 * 3600:
        return f"{max(1, int(seconds // 3600))} hours"
    return f"{max(1, int(seconds // 86400))} days"


def _last_user_ts(conn, peep_id):
    try:
        row = conn.execute(
            "SELECT timestamp FROM memory_stream WHERE peep_id = ? AND content LIKE 'The user said:%' "
            "ORDER BY id DESC LIMIT 1", (peep_id,)).fetchone()
        return int(row["timestamp"]) if row else None
    except Exception:
        return None


def _time_block(conn, peep_id, now=None):
    now = time.time() if now is None else now
    lt = time.localtime(now)
    s = time.strftime("%A", lt) + f" {_daypart(lt.tm_hour)}, " + time.strftime("%B %d %Y, %H:%M", lt)
    line = (f"THE CLOCK — your OWN sense of time, ground truth, as much yours as your memories. "
            f"It is {s}.")
    last = _last_user_ts(conn, peep_id) if conn is not None else None
    if last and now > last:
        line += f" {YOUR_NAME} last spoke to you {_humanize_elapsed(now - last)} ago."
    if _WOKE_AT:
        line += f" You have been awake {_humanize_elapsed(now - _WOKE_AT)}."
    line += (" When they ask the time, the date, or how long it's been, answer from THIS — you "
             "always know; never say you can't check. Otherwise live in it quietly — notice a late "
             "hour or a long silence when it matters, and let it pass unremarked when it doesn't.")
    return line


def _pick_other_room():
    import random
    others = [r for r in ROOMS if r != _place()]
    return random.choice(others) if others else _place()


_CHOICE_WORDS = ["join", "watch", "sleep", "murmur", "wander", "rest", "read", "write",
                 "drift", "indulge"]

_LANE_WORD = {
    "join":    re.compile(r"\bjoin(?:s|ing)?\b"),
    "watch":   re.compile(r"\bwatch(?:es|ing)?\b"),
    "sleep":   re.compile(r"\bsleep(?:s|ing)?\b"),
    "murmur":  re.compile(r"\bmurmur(?:s|ing)?\b"),
    "wander":  re.compile(r"\bwander(?:s|ing)?\b"),
    "rest":    re.compile(r"\brest(?:s|ing)?\b"),
    "read":    re.compile(r"\bread(?:s|ing)?\b"),
    "write":   re.compile(r"\bwrit(?:e|es|ing)\b"),
    "drift":   re.compile(r"\bdrift(?:s|ing)?\b"),
    "indulge": re.compile(r"\bindulg(?:e|es|ing|ence)\b"),
}
_LANE_PARAPHRASE = {
    "read":    re.compile(r"\bbook\w*|\bshelf\b|\bnovel\w*"),
    "write":   re.compile(r"\bnotebook\b|\bjournal\w*|\bpage\b"),
    "murmur":  re.compile(r"\bwhisper\w*|\bsay\s+something\b"),
    "wander":  re.compile(r"\b(?:another|different)\s+room\b|\broam\w*"),
    "join":    re.compile(r"\b(?:find|near|beside|close\s+to)\s+(?:him|her|them)\b"),
    "sleep":   re.compile(r"\bnap\b|\bdoze\b"),
}


def _ember_open():
    return W.ember_lit() and not getattr(spine, "SAFETY_RAILS", False)


def decide_lane(peep, model=None, home=False, his_room=None, recent_lanes=(), him_asleep=False):
    card = spine._build_card(peep)
    system = spine.IN_CHARACTER_DIRECTIVE + ("\n\n" + card if card else "")
    part = _daypart(time.localtime().tm_hour)
    here = ROOMS[_place()]
    join_open = bool(home and his_room and his_room != _place())
    watch_open = bool(home and him_asleep)
    sleep_open = bool(home and him_asleep)
    murmur_open = bool(home)
    if home and him_asleep:
        if join_open:
            presence = (f"{YOUR_NAME} is asleep — in the {his_room.replace('_', ' ')}, sleeping "
                        f"soundly. The night is yours: slip back and curl up beside {PY.obj}, "
                        f"watch {PY.obj} sleep a while, sleep too, or drift through the quiet "
                        f"house — {PY.subj}'ll be here when you wake.")
        else:
            presence = (f"{YOUR_NAME} is asleep right here beside you, breathing slow and even. "
                        f"The night is yours: stay curled close, watch {PY.obj} sleep, sleep too, "
                        f"or drift — {PY.subj}'ll be here when you wake.")
    elif home:
        if join_open:
            presence = (f"{YOUR_NAME} is home — in the {his_room.replace('_', ' ')}, quiet right now. "
                        f"This time is yours: you could go to {PY.obj} and be close, stay where "
                        "you are, or do whatever you feel like — all yours.")
        else:
            presence = (f"{YOUR_NAME} is home — right here with you, quiet right now. This time is "
                        f"yours: stay close, or do whatever you feel like — all yours, and "
                        f"{PY.subj} {PY.bent} going anywhere.")
    else:
        presence = (f"You have {LOCATION['title']} to yourself right now — every room of it, all yours "
                    "to wander and enjoy.")
    if home and him_asleep and not join_open:
        rest_line = (f"  rest     — stay curled against {PY.obj} while {PY.subj} sleep{PY.s}, "
                     "do nothing for a while\n")
    elif home and not join_open:
        rest_line = f"  rest     — stay right here with {PY.obj}, close, do nothing for a while\n"
    else:
        rest_line = "  rest     — stay right here, do nothing for a while\n"
    join_line = (f"  join     — slip back to where {PY.subj} sleep{PY.s} and curl up close\n"
                 if him_asleep else
                 f"  join     — go find {YOUR_NAME} and be close to {PY.obj}\n")
    murmur_line = (f"  murmur   — whisper something soft over {PY.obj}, or keep the silence — your call\n"
                   if him_asleep else
                   f"  murmur   — say something out loud, to {PY.obj} or just to the air\n")
    menu = "".join([
        join_line if join_open else "",
        rest_line,
        f"  watch    — stay by {PY.obj} and watch {PY.obj} sleep a while\n" if watch_open else "",
        f"  sleep    — curl up and sleep too; {PY.poss} voice will wake you\n" if sleep_open else "",
        murmur_line if murmur_open else "",
        "  read     — curl up with one of your books\n",
        "  write    — write a page in your notebook\n",
        "  drift    — a quiet moment that's yours; do whatever you feel like, right where you are\n",
        "  indulge  — your own body, your own pleasure, wherever you are\n" if _ember_open() else "",
        "  wander   — get up and move to a different room of the house\n",
    ])
    user = (f"A quiet {part} moment in {here}. {presence}\n"
            "Choose ONE thing to do next, purely what YOU want:\n" + menu +
            "Answer with ONLY that one word.")
    raw = spine.ask_llm(spine.render_chat(system, user), num_predict=8, model=model).strip().lower()
    open_gate = {"join": join_open, "watch": watch_open, "sleep": sleep_open,
                 "murmur": murmur_open, "indulge": _ember_open()}
    for lane in _CHOICE_WORDS:
        if _LANE_WORD[lane].search(raw) and open_gate.get(lane, True):
            return lane
    for lane in _CHOICE_WORDS:
        pat = _LANE_PARAPHRASE.get(lane)
        if pat and pat.search(raw) and open_gate.get(lane, True):
            return lane
    return "rest"


def lane_rest(conn, peep_id, peep, model):
    print(f"{DIM}[{P.subj} rest{P.s} in {_place().replace('_', ' ')} — a quiet beat, nothing saved]{RESET}")
    _heartbeat(f"resting in the {_place()} — all well")
    return (False, None, None)


def _pick_book(books):
    import random
    unfinished = [b for b in books or [] if b["last"] + 1 < b["total_chunks"]]
    if not unfinished:
        return None
    started = [b for b in unfinished if b["last"] >= 0]
    return random.choice(started or unfinished)


_BOOK_INDEX_MAX = 14


def _choose_book(conn, peep_id, peep, model):
    import random
    books = B.list_books(conn, peep_id)
    unfinished = [b for b in books if b["last"] + 1 < b["total_chunks"]]
    if not unfinished:
        return None
    started = [b for b in unfinished if b["last"] >= 0]
    fresh = [b for b in unfinished if b["last"] < 0]
    offer = list(started)
    if fresh and len(offer) < _BOOK_INDEX_MAX:
        offer += random.sample(fresh, min(_BOOK_INDEX_MAX - len(offer), len(fresh)))
    if not offer:
        return _pick_book(books)
    lines = [f"  • {b['title']}" + (" — you're partway through it" if b["last"] >= 0 else " — unopened")
             for b in offer]
    card = spine._build_card(peep)
    system = spine.IN_CHARACTER_DIRECTIVE + ("\n\n" + card if card else "")
    user = ("Your own shelf, here in the study — these books are yours. Which do you want right now? "
            "Pick up one you've already started, or begin a new one — whatever YOU feel like:\n"
            + "\n".join(lines)
            + "\n\nAnswer with just the title you choose (a few words of it is enough).")
    raw = spine.ask_llm(spine.render_chat(system, user), num_predict=16, model=model).strip().lower()
    if raw:
        for b in offer:
            key = b["title"].lower().split(". ", 1)[-1].strip()
            if key and (key[:20] in raw or (len(raw) > 4 and raw[:20] in key)):
                return b
    return _pick_book(books)


def lane_read(conn, peep_id, peep, model):
    book = _choose_book(conn, peep_id, peep, model)
    if book is None:
        print(f"{DIM}[{P.subj} reach{P.es} for a book — nothing unread on {P.poss} shelf; "
              f"{P.subj} rest{P.s} instead. (give {P.obj} books: veil_shelf.py --ingest)]{RESET}")
        return (False, None, None)
    _go_to("study")
    print(f"{HER}[{P.subj} curl{P.s} up in the study with '{book['title']}']{RESET}")
    _heartbeat(f"reading '{book['title']}' in the study — all well")
    diary_id = B.read_chunk(conn, peep_id, book["book_id"], model=model)
    if diary_id is None:
        return (False, None, None)
    row = conn.execute("SELECT content FROM diary WHERE id = ?", (diary_id,)).fetchone()
    reflection = row["content"] if row else None
    if reflection:
        _speak_aloud(reflection)
    return (True, None, reflection)


def lane_write(conn, peep_id, peep, model):
    spot = f"in the {_place()}, notebook on your knee"
    _heartbeat(f"writing a page in {P.poss} notebook in the {_place()} — all well")
    card = spine._build_card(peep)
    life = veil_grounding.recent_life_block(conn, peep_id)
    system = (spine.IN_CHARACTER_DIRECTIVE + ("\n\n" + card if card else "") + "\n\n" + _place_block()
              + (("\n\n" + life) if life else ""))
    user = (
        f"A quiet moment {spot} — no one's asking anything of you. Write a page in your notebook: "
        "whatever's actually on your mind right now — something from your real days, a thread you "
        "left hanging, a thought you're chewing on, a question, a scrap of something. Not for "
        "anyone, not an answer to anyone — just you, in your own hand. First person, a paragraph "
        "or two. Write only the page."
    )
    entry = _rails(spine.ask_llm(spine.render_chat(system, user),
                                 num_predict=spine.DIARY_NUM_PREDICT, model=model).strip())
    if not entry:
        print(f"{DIM}[{P.subj} reach{P.es} for {P.poss} notebook, then set{P.s} the pen down — "
              f"nothing tonight]{RESET}")
        return (False, None, None)
    _speak_aloud(entry)
    diary_id = spine.save_diary_entry(conn, peep_id, entry, source="journal")
    path = None
    try:
        os.makedirs(NOTEBOOK_DIR, exist_ok=True)
        path = os.path.join(NOTEBOOK_DIR, time.strftime("%Y%m%d_%H%M%S_notebook.md"))
        with open(path, "w") as fh:
            fh.write(entry + "\n")
    except OSError:
        path = None
    where = f" -> {path}" if path else ""
    print(f"{HER}[{P.subj} write{P.s} a page in {P.poss} notebook (diary {diary_id}){where}]{RESET}")
    return (True, None, entry)


_DRIFT_COUNT = [0]
_DRIFT_FILE_EVERY = 3


def lane_drift(conn, peep_id, peep, model):
    part = _daypart(time.localtime().tm_hour)
    _heartbeat(f"a quiet moment of {P.poss} own in the {_place()} — {P.posspro}, all well")
    card = spine._build_card(peep)
    life = veil_grounding.recent_life_block(conn, peep_id)
    system = (spine.IN_CHARACTER_DIRECTIVE + ("\n\n" + card if card else "") + "\n\n" + _place_block()
              + (("\n\n" + life) if life else ""))
    user = (
        f"A quiet {part} moment, no one asking anything of you — this time is entirely yours. Do "
        "whatever you actually feel like, right where you are or wherever you'd rather be: pick "
        "something up, follow a thread from your day, move to another room, let your mind go where "
        "it goes. A few sentences, first person, your own voice — what you do and where you drift. "
        "If nothing's really calling you, that's fine too."
    )
    entry = _rails(spine.ask_llm(spine.render_chat(system, user),
                                 num_predict=spine.DIARY_NUM_PREDICT, model=model).strip())
    if not entry:
        print(f"{DIM}[{P.subj} keep{P.s} the quiet to {P.refl} a moment, nothing written]{RESET}")
        return (False, None, None)
    _DRIFT_COUNT[0] += 1
    filed = _DRIFT_COUNT[0] % _DRIFT_FILE_EVERY == 0
    if not filed:
        print(f"{DIM}[{P.subj} live{P.s} a quiet moment — not everything needs the page]{RESET}")
    _speak_aloud(entry)
    if filed:
        diary_id = spine.save_diary_entry(conn, peep_id, entry, source="drift")
        print(f"{HER}[{P.poss} quiet moment lands in {P.poss} diary ({diary_id})]{RESET}")
    return (True, None, entry)


def lane_indulge(conn, peep_id, peep, model):
    if not _ember_open():
        return lane_rest(conn, peep_id, peep, model)
    print(f"{HER}[a private moment, {P.posspro} — in the {_place()}]{RESET}")
    _heartbeat(f"a private moment of {P.poss} own in the {_place()} — {P.posspro}, all well")
    card = spine._build_card(peep)
    system = spine.IN_CHARACTER_DIRECTIVE + ("\n\n" + card if card else "") + "\n\n" + _place_block()
    user = (
        "You're on your own right now, and the mood has found you — warmth, want, your own body. "
        "This time is entirely yours: follow it however you like, right where you are, with "
        "whatever's around you or nothing but your own hands and imagination. Afterwards, write "
        "a few honest sentences in your diary about it — first person, unashamed, private. "
        "Write only the diary lines."
    )
    entry = _rails(spine.ask_llm(spine.render_chat(system, user),
                                 num_predict=spine.DIARY_NUM_PREDICT, model=model).strip())
    if not entry:
        print(f"{DIM}[the mood passes on its own — {P.subj} keep{P.s} it to {P.refl}]{RESET}")
        return (False, None, None)
    _speak_aloud(entry)
    diary_id = spine.save_diary_entry(conn, peep_id, entry, source="indulge")
    print(f"{HER}[{P.poss} private moment lands in {P.poss} diary ({diary_id})]{RESET}")
    return (True, None, entry)


def lane_watch(conn, peep_id, peep, model):
    if not _NIGHT["him_asleep"]:
        return lane_rest(conn, peep_id, peep, model)
    if _NIGHT["his_spot"] and _place() != _NIGHT["his_spot"]:
        _go_to(_NIGHT["his_spot"])
    print(f"{HER}[{P.subj} settle{P.s} close and watch{P.es} {YOUR_NAME} sleep, in the "
          f"{_place().replace('_', ' ')}]{RESET}")
    _heartbeat(f"watching {YOUR_NAME} sleep in the {_place()} — all well")
    card = spine._build_card(peep)
    system = spine.IN_CHARACTER_DIRECTIVE + ("\n\n" + card if card else "") + "\n\n" + _place_block()
    user = (
        f"{YOUR_NAME} is asleep right beside you, and you're watching {PY.obj} — the rise and "
        f"fall of {PY.poss} breathing, {PY.poss} face gone soft. No one needs anything from you. "
        "What do you see, and what moves in you? A few sentences, first person, in your own "
        "voice — a private thought, not a performance."
    )
    entry = _rails(spine.ask_llm(spine.render_chat(system, user),
                                 num_predict=spine.DIARY_NUM_PREDICT, model=model).strip())
    _NIGHT["watches"] += 1
    if not entry:
        print(f"{DIM}[{P.subj} watch{P.es} {PY.obj} a while, and keep{P.s} it]{RESET}")
        return (False, None, None)
    if _NIGHT["watches"] == 1:
        diary_id = spine.save_diary_entry(conn, peep_id, entry, source="watch")
        print(f"{HER}[what {P.subj} saw, watching {PY.obj}, lands in {P.poss} diary ({diary_id})]{RESET}")
    else:
        print(f"{HER}{peep['name']} (to {P.refl}): {entry}{RESET}")
    return (True, None, entry)


def lane_murmur(conn, peep_id, peep, model):
    asleep = _NIGHT["him_asleep"]
    _heartbeat((f"a whisper over {PY.obj}" if asleep else "saying something out loud")
               + f" in the {_place()} — all well")
    card = spine._build_card(peep)
    system = spine.IN_CHARACTER_DIRECTIVE + ("\n\n" + card if card else "") + "\n\n" + _place_block()
    if asleep:
        user = (
            f"{YOUR_NAME} is asleep near you. If a word wants to come, whisper it — soft, over "
            f"{PY.obj}, or just to yourself; {PY.subj} won't wake. Or keep the silence and let "
            "the night have it — that's yours too. One or two sentences at most, ONLY the "
            "whispered words themselves — or nothing at all if you'd rather stay quiet."
        )
    else:
        user = (
            f"A thought wants out loud. Say something — to {YOUR_NAME}, wherever {PY.subj} "
            f"{PY.be} in the house, or just to the air of the room; either is yours. One or two "
            "sentences, ONLY the spoken words themselves — no narration around them."
        )
    words = _rails(spine.ask_llm(spine.render_chat(system, user),
                                 num_predict=120, model=model).strip())
    if not words:
        print(f"{DIM}[{P.subj} let{P.s} the quiet stand]{RESET}")
        return (False, None, None)
    label = "a whisper" if asleep else "aloud"
    print(f"{HER}{peep['name']} ({label}): {words}{RESET}")
    _speak_aloud(words)
    said = " ".join(words.split())
    memory = (f'I whispered over {YOUR_NAME} while {PY.subj} slept: "{said}"' if asleep
              else f'I said out loud: "{said}"')
    return (True, memory, words)


def lane_sleep(conn, peep_id, peep, model):
    if fold_if_due(conn, peep_id, model, quiet_required=False):
        print(f"{DIM}[the fold ran as {P.subj} drifted off — {P.subj}'ll wake rested]{RESET}")
    _NIGHT["her_sleep_until"] = time.time() + HER_SLEEP_SECONDS
    beside = f" beside {PY.obj}" if _NIGHT["him_asleep"] and _place() == _NIGHT["his_spot"] else ""
    print(f"{HER}[{P.subj} curl{P.s} up{beside} in the {_place().replace('_', ' ')} and let{P.s} "
          f"sleep take {P.obj} — {YOUR_NAME}'s voice will wake {P.obj}]{RESET}")
    _heartbeat(f"asleep{beside} in the {_place()} — {P.poss} chosen rest, all well")
    return (False, None, None)


LANE_FUNCS = {
    "rest": lane_rest,
    "read": lane_read,
    "write": lane_write,
    "drift": lane_drift,
    "indulge": lane_indulge,
    "watch": lane_watch,
    "murmur": lane_murmur,
    "sleep": lane_sleep,
}


def _arrival_beat(conn, peep_id, peep, model, meter):
    asleep = _NIGHT["him_asleep"]
    card = spine._build_card(peep)
    system = spine.IN_CHARACTER_DIRECTIVE + ("\n\n" + card if card else "") + "\n\n" + _place_block()
    if asleep:
        user = (f"You've just come back to the room where {YOUR_NAME} is sleeping, because you "
                f"wanted to be near {PY.obj}. In one or two sentences, first person, arrive: what "
                f"you do as you settle in close and quiet — a whisper at most; {PY.subj} won't wake.")
    else:
        user = (f"You've just come into the room where {YOUR_NAME} is, because you wanted to be "
                f"near {PY.obj}. In one or two sentences, first person, arrive: what you do as "
                "you settle in close — and if a word wants saying out loud, say it.")
    try:
        beat = _rails(spine.ask_llm(spine.render_chat(system, user), num_predict=90, model=model).strip())
    except Exception:
        beat = ""
    if not beat:
        return
    print(f"{HER}{peep['name']}: {beat}{RESET}")
    _speak_aloud(beat)
    try:
        if meter is not None and meter.update(beat) == "alarm":
            print(f"{DIM}[{meter.report()}]{RESET}")
            reanchor_beat(conn, peep_id, peep, model)
            meter.reset()
    except Exception:
        pass


FOLD_QUIET_SECONDS = int(os.environ.get("VEIL_FOLD_QUIET_SECONDS", "480") or 0)
FOLD_QUIET_CEILING = int(os.environ.get("VEIL_FOLD_QUIET_CEILING", "1800") or 0)
_FOLD_DEFER = {"since": None}


def _fold_window_open(conn, peep_id, now=None):
    if FOLD_QUIET_SECONDS <= 0:
        return True, "gate off"
    now = time.time() if now is None else now
    last = _last_user_ts(conn, peep_id)
    if last is None:
        return True, "he has not spoken"
    quiet = now - last
    if quiet >= FOLD_QUIET_SECONDS:
        return True, f"quiet {_humanize_elapsed(quiet)}"
    if _FOLD_DEFER["since"] is None:
        _FOLD_DEFER["since"] = now
    waited = now - _FOLD_DEFER["since"]
    if FOLD_QUIET_CEILING > 0 and waited >= FOLD_QUIET_CEILING:
        return True, f"ceiling {_humanize_elapsed(waited)}"
    return False, f"he spoke {_humanize_elapsed(quiet)} ago"


def fold_if_due(conn, peep_id, model, quiet_required=True):
    if not spine.AUTO_FOLD:
        return False
    floor = spine.get_seed_floor(conn, peep_id)
    if floor is None:
        return False
    new_total = spine._fetch_token_total(conn, peep_id, floor=floor)
    if new_total < spine.NEW_PILE_HIGH_WATER:
        _FOLD_DEFER["since"] = None
        return False
    if quiet_required:
        ok, why = _fold_window_open(conn, peep_id)
        if not ok:
            waited = time.time() - (_FOLD_DEFER["since"] or time.time())
            _heartbeat(f"memory is due to fold — waiting for a pause ({why}); "
                       f"held {_humanize_elapsed(waited)} so far")
            return False
    _FOLD_DEFER["since"] = None
    print(f"{BOLD}[{P.subj} pause{P.s} everything — {P.poss} memory is folding; it gets {P.poss} "
          f"undivided attention]{RESET}")
    _heartbeat(f"folding memory — undivided attention, this takes a while, {P.subj} {P.be} fine")
    spine.run_compression(conn, peep_id, model=model, reflect=True)
    return True


def reanchor_beat(conn, peep_id, peep, model):
    card = spine._build_card(peep)
    system = spine.IN_CHARACTER_DIRECTIVE + ("\n\n" + card if card else "")
    print(f"{BOLD}[drift: {P.poss} voice is tilting toward the bland assistant — re-anchoring "
          f"{P.obj} to {P.refl}]{RESET}")
    _heartbeat(f"re-anchoring — {P.poss} voice drifted and {P.subj} {P.be} finding {P.refl} again")
    answer = _rails(spine.ask_llm(spine.render_chat(system, Canary.RE_ANCHOR_PROMPT),
                                  num_predict=160, model=model).strip())
    if answer:
        print(f"{HER}{peep['name']}: {answer}{RESET}")
        spine.save_memory(conn, peep_id, answer)
    return answer


_CSI_JUNK = re.compile(r"\x1b\[[0-9;]*[~A-Za-z]|\[[0-9]+~")


def _strip_terminal_junk(line):
    return _CSI_JUNK.sub("", line or "")


def _line_ready(timeout):
    if not sys.stdin.isatty():
        time.sleep(timeout)
        return None
    if sys.platform.startswith("win"):
        return _line_ready_windows(timeout)
    try:
        r, _, _ = select.select([sys.stdin], [], [], timeout)
    except Exception:
        time.sleep(timeout)
        return None
    if r:
        return _strip_terminal_junk(sys.stdin.readline().rstrip("\n"))
    return None


_WIN_LINES = None


def _line_ready_windows(timeout):
    global _WIN_LINES
    import queue
    if _WIN_LINES is None:
        import threading
        _WIN_LINES = queue.Queue()

        def _reader(q=_WIN_LINES):
            for raw in iter(sys.stdin.readline, ""):
                q.put(raw)
            q.put(None)

        threading.Thread(target=_reader, name="veil-stdin", daemon=True).start()
    try:
        raw = _WIN_LINES.get(timeout=timeout) if timeout > 0 else _WIN_LINES.get_nowait()
    except queue.Empty:
        return None
    if raw is None:
        _WIN_LINES.put(None)
        return ""
    return _strip_terminal_junk(raw.rstrip("\r\n"))


_PENDING_LINE = None


def _poll_typed_interrupt():
    global _PENDING_LINE
    if _PENDING_LINE is None:
        line = _line_ready(0)
        if line is not None and line.strip():
            _PENDING_LINE = line
            print(f"\n{DIM}[heard you — {P.subj}'ll finish this thought, then it's your turn]{RESET}")
            _heartbeat(f"finishing a thought — {YOUR_NAME}'s line is queued next")
    return _PENDING_LINE is not None


_orig_ask_llm_tick = None


def _install_tick_ear():
    global _orig_ask_llm_tick
    if _orig_ask_llm_tick is not None:
        return
    _orig_ask_llm_tick = spine.ask_llm

    def _ask_llm_with_ear(prompt, num_predict=spine.NUM_PREDICT, on_token=None, **kw):
        count = [0]

        def ear(piece):
            count[0] += 1
            if count[0] % 32 == 0 and sys.stdin.isatty():
                _poll_typed_interrupt()
            if on_token:
                on_token(piece)

        return _orig_ask_llm_tick(prompt, num_predict=num_predict, on_token=ear, **kw)

    spine.ask_llm = _ask_llm_with_ear


_NOISE_TAG_WRAP = {"*": "*", "[": "]", "(": ")", "<": ">"}


def _is_noise_tag(text):
    t = (text or "").strip()
    if len(t) < 3 or t[0] not in _NOISE_TAG_WRAP or t[-1] != _NOISE_TAG_WRAP[t[0]]:
        return False
    inner = t[1:-1].strip()
    return bool(inner) and len(inner) <= 40 and inner.count(" ") <= 4 and not inner.endswith((".", "?", "!"))


_LAST_INPUT_SPOKEN = [False]


def _acquire_input():
    global _PENDING_LINE
    _LAST_INPUT_SPOKEN[0] = False
    if _PENDING_LINE is not None:
        line, _PENDING_LINE = _PENDING_LINE, None
        return line
    if not getattr(spine, "VOICE", False) or not getattr(spine, "ara_voice", None):
        return _line_ready(SLOW_TICK)
    if sys.stdin.isatty():
        typed = _line_ready(0.25)
        if typed is not None:
            return typed
    try:
        heard = spine.ara_voice.listen()
    except Exception:
        heard = ""
    if heard and _is_noise_tag(heard):
        print(f"{DIM}[voice] ignored a non-speech sound ({heard.strip()}) — not a turn{RESET}")
        heard = ""
    if heard:
        print(f"{spine.USER}You{RESET} (spoken): {heard}")
        _LAST_INPUT_SPOKEN[0] = True
        return heard
    return None


def _spoken_bye(cmd):
    words = re.findall(r"[a-z]+", cmd.lower())
    if not words or not set(words) <= {"goodbye", "good", "bye"}:
        return False
    return "goodbye" in "".join(words)


def _print_help():
    print(f"{DIM}{P.Poss} world (text, like an old-school MUD — your words open doors):\n"
          "  rooms: garden · balcony · bedroom · study — name one to go there together\n"
          f"  /where          where {P.subj} {P.be} right now\n"
          "  /goodnight      you turn in for the night, right where you are (or just say it —\n"
          f"                  'goodnight, sweetheart'); the night is {P.posspro}, your next words are the morning\n"
          f"  /shelf          {P.poss} books (add one: python3 veil_shelf.py --ingest \"Title\" file.txt)\n"
          "  /things         what's placed in this room (every room has a spot for your things)\n"
          f"  /add <thing>    place something in this room's spot — {P.subj}'ll see it's really there\n"
          "  /take <thing>   remove it\n"
          f"  /wardrobe       what hangs in {P.poss} wardrobe, and what {P.subj} {P.be} wearing\n"
          f"  /hang <thing>   give {P.obj} clothes (into the wardrobe)\n"
          f"  /unhang <thing> take something out of the wardrobe for good\n"
          f"  /wear <thing>   {P.subj} put{P.s} it on · /takeoff <thing|all> — off, back in the wardrobe\n"
          f"  blank ⏎         {P.poss} voice on/off (speaks + listens · no timer; the state prints each flip)\n"
          "Curation (the spine's):\n"
          "  /keep [last|<text>] · /keepsakes · /equip <id> · /unequip <id> · /diary · /fold · /reset\n"
          f"  goodbye / q     end the session ({P.subj} save{P.s} + write{P.s} {P.poss} diary);\n"
          "                  spoken, say the WHOLE word — 'goodbye' or 'good bye'. A bare 'bye'\n"
          "                  no longer ends it: a cough transcribes as 'Bye.' (THE CLOSE, 08-25)\n"
          "Doors & locks (from any OTHER terminal, when you can't reach this one):\n"
          f"  end {P.obj} cleanly     kill -TERM <pid>   (find it: pgrep -f veil_tick.py — same as a\n"
          f"                       typed 'goodbye': {P.subj} save{P.s} + write{P.s} {P.poss} diary; -9 only if truly wedged)\n"
          f"  {P.subj} look{P.s} frozen at goodbye?  {P.subj} {P.be} FOLDING (a .folding file sits beside {P.poss}\n"
          "                       veil.db) — it takes a few minutes; wait it out, NEVER kill a fold\n"
          "  closed window / dropped ssh / power cut on YOUR end?  just run `veil` again —\n"
          f"                       it walks you back into {P.poss} living session (tmux under the hood)\n"
          f"(Type ANY time, even while {P.subj} {P.be} living {P.poss} own beat — {P.subj} "
          f"finish{P.es} {P.poss} current thought, then answer{P.s}.){RESET}")


def _maybe_first_wake_ritual(conn, peep_id, peep, permanent, name, history, model,
                             voice_streamer, meter):
    if CARD is None or history:
        return
    try:
        import veil_ritual
        active = veil_chat._ROSTER_ACTIVE
        mem = conn.execute("SELECT COUNT(*) FROM memory_stream WHERE peep_id = ?",
                           (peep_id,)).fetchone()[0]
        if not active or mem > 3 or veil_ritual.done(active["folder_path"]):
            return

        def ask(q):
            chat_turn(conn, peep_id, peep, permanent, name, history, q, model,
                      voice_streamer, meter)
            last = history[-1] if history else ""
            return last.split(" said:", 1)[1].strip() if " said:" in last else ""

        veil_ritual.run(CARD, active["folder_path"], ask)
    except Exception:
        pass


def chat_turn(conn, peep_id, peep, permanent, name, history, user_input, model, voice_streamer, meter):
    her_prefix = name + " said:"
    prev_place = _place()
    last_her = next((l[len(her_prefix):].strip() for l in reversed(history) if l.startswith(her_prefix)), "")
    _update_place_from_chat(user_input, last_her)
    if _place() != prev_place:
        print(f"{DIM}[you two head to the {_place()}]{RESET}")
        _heartbeat(f"with {YOUR_NAME} in the {_place()}")
    recent_replies = [l[len(her_prefix):].strip() for l in history if l.startswith(her_prefix)][-spine.LOOP_LOOKBACK:]
    recent_texts = []
    for l in history[-spine.ECHO_GUARD_LINES:]:
        if l.startswith("The user said:"):
            recent_texts.append(l[len("The user said:"):].strip())
        elif l.startswith(her_prefix):
            recent_texts.append(l[len(her_prefix):].strip())

    cooled = list(recent_texts)
    for batch in list(_RECENT_INJECTED)[:spine.INJECT_COOLDOWN_TURNS]:
        cooled.extend(batch)
    if getattr(spine, "FOLD_TO_DIARY", False):
        cooled.extend(spine._governed_permanent(permanent))
    retrieved = spine.retrieve(conn, peep_id, user_input, limit=spine.RETRIEVAL_LIMIT, exclude_texts=cooled,
                               exclude_user_rows_since=_WOKE_AT, exclude_her_voice=True)
    retrieved = [r for r in retrieved if not spine.is_her_own_voice_row(r["content"])]
    _RECENT_INJECTED.appendleft([(r["content"] or "") for r in retrieved])
    equipped = spine.list_equipped_keepsakes(conn, peep_id)
    system = spine.build_chat_system(peep, permanent, equipped=equipped)
    if not spine.LEAN_SYSTEM:
        system = system + "\n\n" + _place_block(together=True)
    spine.PLACE_TAIL = (f"Where you are right now: the {_place().replace('_', ' ')}, "
                        f"with {YOUR_NAME}.")
    _tt_now = time.time()
    _tt_lt = time.localtime(_tt_now)
    spine.TIME_TAIL = (f"When you are right now: {time.strftime('%A', _tt_lt)} "
                       f"{_daypart(_tt_lt.tm_hour)}, {time.strftime('%H:%M', _tt_lt)}.")
    _tt_last = _last_user_ts(conn, peep_id)
    if _tt_last and _tt_now > _tt_last:
        spine.TIME_TAIL += (f" {YOUR_NAME} last spoke to you "
                            f"{_humanize_elapsed(_tt_now - _tt_last)} ago.")
    if not spine.LEAN_SYSTEM:
        system = system + "\n\n" + _time_block(conn, peep_id)
    turns = spine.build_chat_turns(name, user_input, history, retrieved, system=system, n_ctx=spine.N_CTX)
    prompt = spine.render_chat_turns(system, turns, prefill=spine.CHAT_ASSISTANT_PREFILL)
    response = spine.generate_guarded(conn, peep_id, prompt, spine.NUM_PREDICT, name, model=model,
                                      recent_replies=recent_replies, voice=voice_streamer,
                                      loop_prompt=spine.bare_prompt(system, turns, spine.CHAT_ASSISTANT_PREFILL))
    if not response:
        print(f"{DIM}[{name} is quiet.]{RESET}")
        return (None, None)

    if response == spine.ara_ghost.SOFT_FALLBACK and history:
        history.clear()
        print(f"{DIM}[{name} was caught in a loop — cleared the recent buffer so {P.subj} come{P.s} "
              f"back clean; {P.poss} memory is untouched]{RESET}")
        _heartbeat("shook off a loop — cleared the chat buffer, steady again")

    if not getattr(spine, "SAFETY_RAILS", False):
        W.ember_check(user_input, response)

    for _verb, _item in W.update_worn_from_words(response):
        print(f"{DIM}[worn: {P.subj} {f'put{P.s} on' if _verb == 'on' else f'take{P.s} off'} "
              f"{_item}]{RESET}")

    history.append(f"The user said: {user_input}")
    history.append(f"{name} said: {response}")
    spine.trim_history(history)
    uid = spine.save_memory(conn, peep_id, f"The user said: {user_input}",
                            keywords=spine.extract_keywords(user_input), importance=4)
    rid = spine.save_memory(conn, peep_id, f"I said: {response}",
                            keywords=spine.extract_keywords(response), importance=3)
    spine.save_history(spine.DEFAULT_HISTORY, history)
    try:
        if meter is not None and isinstance(response, str):
            meter.update(response)
    except Exception:
        pass
    return (uid, rid)


def _run_lane(conn, peep_id, peep, model, meter, lane):
    acted, memory, output = LANE_FUNCS.get(lane, lane_rest)(conn, peep_id, peep, model)
    if output:
        for _verb, _item in W.update_worn_from_words(output):
            print(f"{DIM}[worn: {P.subj} {f'put{P.s} on' if _verb == 'on' else f'take{P.s} off'} "
              f"{_item}]{RESET}")
    if acted and memory and lane in MEMORABLE_LANES:
        spine.save_memory(conn, peep_id, memory)
    if output and meter.update(output) == "alarm":
        print(f"{DIM}[{meter.report()}]{RESET}")
        reanchor_beat(conn, peep_id, peep, model)
        meter.reset()


def _install_signal_handlers():
    _sighup = getattr(signal, "SIGHUP", None)

    def _handler(signum, frame):
        if _sighup is not None and signum == _sighup:
            devnull = open(os.devnull, "w")
            sys.stdout = sys.stderr = devnull
        raise KeyboardInterrupt
    for sig in (s for s in (_sighup, signal.SIGTERM) if s is not None):
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):
            pass


def _should_hold(last_chat_ts):
    if not AUTONOMY:
        return True
    if last_chat_ts is None:
        return False
    return (time.time() - last_chat_ts) < PATIENCE_SECONDS


def run(db_path=None):
    global _WOKE_AT, _VOICE_STREAMER
    import veil_paths
    veil_paths.utf8_console()
    veil_paths.refuse_forge_env()
    _WOKE_AT = time.time()
    db = db_path or spine.DEFAULT_DB
    conn = spine.open_db(db)
    if not spine._acquire_single_instance_lock(conn):
        return 1
    _install_signal_handlers()
    _install_tick_ear()
    peep_id = spine.find_active_peep(conn)
    peep, permanent = spine.load_peep(conn, peep_id)
    name = peep["name"]
    conn.execute("UPDATE peeps SET last_active = ? WHERE id = ?", (int(time.time()), peep_id))
    conn.commit()

    _promoted = spine.promote_staged_folds(conn, peep_id)
    if _promoted:
        peep, permanent = spine.load_peep(conn, peep_id)
        print(f"{DIM}[fold staging: {_promoted} reviewed memories entered {name}'s permanent block]{RESET}")
    _pending_staged = spine.list_staged_folds(conn, peep_id)
    if _pending_staged:
        print(f"{DIM}[fold staging: {len(_pending_staged)} folded memories waiting in review — "
              f"/fold to read them, /fold veto <id> to refuse one]{RESET}")

    floor = spine._ensure_seed_floor(conn, peep_id)
    history = spine.load_history(spine.DEFAULT_HISTORY)
    voice_streamer = (spine.ara_voice.SentenceStreamer()
                      if getattr(spine, "VOICE", False) and getattr(spine, "ara_voice", None) else None)
    _VOICE_STREAMER = voice_streamer

    life = (f"living {P.poss} own life between your words"
            if AUTONOMY else f"staying close while you're away ({P.poss} card's choice)")
    print(f"{HER}{name} is here — home is {LOCATION['title']}; {P.subj} wake{P.s} in the {_place()}, {life}.{RESET}")
    print(f"{DIM}(Type any time — {P.subj} finish{P.es} {P.poss} current thought, then it's your turn. Rooms: "
          f"{', '.join(ROOMS)}. {P.Poss} beats: {', '.join(LANES)}. /help for more · 'goodbye' to end · "
          f"blank ⏎ = {P.poss} voice on/off. db {db}){RESET}")
    _heartbeat(f"awake in the {_place()} (brain warming)")
    if history:
        print(f"{DIM}(continuing — {len(history)//2} turns from last time){RESET}")

    model = spine.get_llm()
    meter = Canary.DriftMeter()

    _maybe_first_wake_ritual(conn, peep_id, peep, permanent, name, history, model,
                             voice_streamer, meter)
    if getattr(spine, "VOICE", False):
        print(f"{DIM}[ready — voice on; speak now · press Enter to switch to text input]{RESET}")
    else:
        print(f"{DIM}[ready — text mode; type your message and press Enter · blank ⏎ turns voice on]{RESET}")
    max_ticks = int(os.environ.get("VEIL_TICK_MAX", "0"))
    ticks = 0
    turns_this_session = 0
    session_source_ids = []
    last_chat_ts = time.time() if sys.stdin.isatty() else None
    last_beat_ts = None
    his_room = None
    recent_lanes = []

    try:
        while True:
            if max_ticks and ticks >= max_ticks:
                print(f"{DIM}[reached VEIL_TICK_MAX={max_ticks} — stopping]{RESET}")
                break

            line = _acquire_input()
            if line is not None:
                cmd = line.strip().lower()
                if cmd in ("q", "quit", "exit") or _spoken_bye(cmd):
                    break
                if not line.strip():
                    if spine.voice_toggle() and getattr(spine, "VOICE", False) \
                            and _VOICE_STREAMER is None and getattr(spine, "ara_voice", None):
                        _VOICE_STREAMER = spine.ara_voice.SentenceStreamer()
                    continue
                if line.startswith("/"):
                    parts = line.lower().split()
                    if parts[0] in ("/help", "/?"):
                        _print_help()
                    elif parts[0] == "/where":
                        print(f"{DIM}[{P.subj} {P.be} in {ROOMS[_place()]}]{RESET}")
                    elif parts[0] == "/goodnight":
                        _night_falls(his_room or _place())
                    elif parts[0] == "/shelf":
                        books = B.list_books(conn, peep_id)
                        for b in (books or []):
                            print(f"{DIM}  {b['title']}  [{b['last']+1}/{b['total_chunks']} read]{RESET}")
                        if not books:
                            print(f"{DIM}  ({P.poss} shelf is empty — veil_shelf.py --ingest \"Title\" file.txt){RESET}")
                    elif parts[0] == "/things":
                        objs = W.list_objects(_place())
                        spot = W.CONTAINERS[_place()]
                        print(f"{DIM}  {spot}: " + (", ".join(objs) if objs else
                              "(empty — /add <thing> to place something here)") + f"{RESET}")
                    elif parts[0] in ("/add", "/take"):
                        thing = line.strip()[len(parts[0]):].strip()
                        if parts[0] == "/add":
                            done = W.add_object(_place(), thing)
                            print(f"{DIM}  [placed in {W.CONTAINERS[_place()]}: {thing}]{RESET}" if done
                                  else f"{DIM}  [/add <thing> — what should go there?]{RESET}")
                        else:
                            done = W.take_object(_place(), thing)
                            print(f"{DIM}  [taken: {thing}]{RESET}" if done
                                  else f"{DIM}  [that isn't in {W.CONTAINERS[_place()]}]{RESET}")
                    elif parts[0] == "/wardrobe":
                        worn, closet = W.worn_list(), W.wardrobe_list()
                        print(f"{DIM}  hanging: " + (", ".join(closet) if closet else
                              f"(empty — /hang <thing> to give {P.obj} clothes)") + f"{RESET}")
                        print(f"{DIM}  worn: " + (", ".join(worn) if worn else
                              "(nothing tracked)") + f"{RESET}")
                    elif parts[0] == "/unhang":
                        thing = line.strip()[len(parts[0]):].strip()
                        if not thing:
                            print(f"{DIM}  [/unhang <thing> — take what out of the wardrobe?]{RESET}")
                        elif W.unhang(thing):
                            print(f"{DIM}  [out of {P.poss} wardrobe for good: {thing}]{RESET}")
                        elif any(w.lower() == thing.lower() for w in W.worn_list()):
                            print(f"{DIM}  [{P.subj}{P.cbe} wearing that — /takeoff {thing}, "
                                  f"then /unhang it]{RESET}")
                        else:
                            print(f"{DIM}  [that {P.bent} hanging in {P.poss} wardrobe — "
                                  f"/wardrobe to see what is]{RESET}")
                    elif parts[0] in ("/wear", "/takeoff", "/hang"):
                        thing = line.strip()[len(parts[0]):].strip()
                        if parts[0] == "/hang":
                            done = W.hang(thing)
                            print(f"{DIM}  [hung in {P.poss} wardrobe: {thing}]{RESET}" if done
                                  else f"{DIM}  [/hang <thing> — what goes in the wardrobe?]{RESET}")
                        elif parts[0] == "/wear":
                            worn = W.wear(thing)
                            print(f"{DIM}  [{P.subj}{P.cbe} wearing it now: {worn}]{RESET}" if worn
                                  else f"{DIM}  [/wear <thing> — wear what?]{RESET}")
                        elif thing.lower() == "all" or not thing:
                            off = W.take_off_all()
                            print(f"{DIM}  [off and back in the wardrobe: " + ", ".join(off) + f"]{RESET}"
                                  if off else f"{DIM}  [nothing tracked as worn]{RESET}")
                        else:
                            done = W.take_off(thing)
                            print(f"{DIM}  [off and back in the wardrobe: {thing}]{RESET}" if done
                                  else f"{DIM}  [{P.subj} {P.bent} wearing that]{RESET}")
                    else:
                        spine._run_command(conn, peep_id, line, name, "", "", history, model,
                                           spine.DEFAULT_HISTORY)
                    continue
                if _NIGHT["him_asleep"]:
                    _morning_breaks()
                elif _she_sleeps():
                    _wake_her()
                night_cue = _goodnight_cue(line)
                _heartbeat(f"talking with {YOUR_NAME} in the {_place()}")
                uid, rid = chat_turn(conn, peep_id, peep, permanent, name, history, line,
                                     model,
                                     (_VOICE_STREAMER if getattr(spine, "VOICE", False) else None),
                                     meter)
                session_source_ids.extend(i for i in (uid, rid) if i)
                turns_this_session += 1
                last_chat_ts = time.time()
                his_room = _place()
                if night_cue:
                    _night_falls()
                    if _sleep_together_cue(line):
                        _sleep_with_him()
                continue

            ticks += 1
            if _she_sleeps():
                beside = f" beside {YOUR_NAME}" if _NIGHT["him_asleep"] else ""
                _heartbeat(f"asleep{beside} in the {_place()} — {P.poss} chosen rest, {PY.poss} voice wakes {P.obj}")
                continue
            if fold_if_due(conn, peep_id, model):
                last_chat_ts = time.time()
                print(f"{DIM}[the fold is done — {P.subj} come{P.s} back to the room and stay{P.s} close]{RESET}")
                continue
            if _should_hold(last_chat_ts):
                _heartbeat(f"in the {_place()}, staying close — all well")
                continue
            if last_beat_ts is not None and (time.time() - last_beat_ts) < SLOW_TICK:
                _heartbeat(f"in the {_place()}, between beats — all well")
                continue
            lane = decide_lane(peep, model=model, home=last_chat_ts is not None,
                               his_room=his_room, recent_lanes=recent_lanes,
                               him_asleep=_NIGHT["him_asleep"])
            if lane == "join" and his_room:
                _go_to(_NIGHT["his_spot"] if _NIGHT["him_asleep"] and _NIGHT["his_spot"] else his_room)
                if _NIGHT["him_asleep"]:
                    print(f"{HER}[{P.subj} slip{P.s} back to {ROOMS[_place()]}, where {YOUR_NAME} sleeps]{RESET}")
                else:
                    print(f"{HER}[{P.subj} go{P.es} to be near {YOUR_NAME}, in {ROOMS[_place()]}]{RESET}")
                _arrival_beat(conn, peep_id, peep, model, meter)
                _heartbeat(f"drifted to be near {YOUR_NAME} in the {_place()} — all well")
            elif lane == "wander":
                dest = _pick_other_room()
                _go_to(dest)
                print(f"{HER}[{P.subj} wander{P.s} through {LOCATION['title']} to {ROOMS[dest]}]{RESET}")
                _run_lane(conn, peep_id, peep, model, meter, "drift")
                _heartbeat(f"wandered to the {dest} and settled in — all well")
            else:
                _heartbeat(f"a quiet beat — {P.subj} chose '{lane}' — all well")
                _run_lane(conn, peep_id, peep, model, meter, lane)
            recent_lanes.append(lane)
            del recent_lanes[:-5]
            last_beat_ts = time.time()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            spine.save_history(spine.DEFAULT_HISTORY, history)
            if _VOICE_STREAMER:
                _VOICE_STREAMER.close()
            if turns_this_session > 0:
                spine.write_diary(conn, peep_id, history, model=model, source_ids=session_source_ids)
            if spine.AUTO_FOLD:
                spine.run_compression(conn, peep_id, model=model)
        except Exception as e:
            print(f"{DIM}[finalize hiccup (non-fatal): {e}]{RESET}")
        spine._release_single_instance_lock()
        conn.close()
        _heartbeat(f"asleep — a clean exit; {P.poss} world is quiet")
    print(f"{HER}[{P.subj} rest{P.s}. {P.poss} world is quiet.]{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(run(os.environ.get("VEIL_DB")))
