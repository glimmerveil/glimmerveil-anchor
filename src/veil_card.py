#!/usr/bin/env python3

import dataclasses
import json
import os
import re
import sys
import time

CARD_VERSION = 1

DEFAULT_CARD_JSON = os.environ.get("VEIL_CARD_JSON", os.path.expanduser("~/anchor/card.json"))


PRONOUN_SETS = {
    "she/her":   dict(subj="she", obj="her", poss="her", posspro="hers", refl="herself",
                      s="s", es="es", be="is", bent="isn't", has="has", cbe="'s"),
    "he/him":    dict(subj="he", obj="him", poss="his", posspro="his", refl="himself",
                      s="s", es="es", be="is", bent="isn't", has="has", cbe="'s"),
    "they/them": dict(subj="they", obj="them", poss="their", posspro="theirs", refl="themself",
                      s="", es="", be="are", bent="aren't", has="have", cbe="'re"),
}


class Pronouns:

    def __init__(self, spec):
        base = PRONOUN_SETS.get(_normalize_pronouns(spec))
        for k, v in base.items():
            setattr(self, k, v)
        self.Subj = self.subj.capitalize()
        self.Poss = self.poss.capitalize()
        self.spec = _normalize_pronouns(spec)


def _normalize_pronouns(spec):
    s = (spec or "").strip().lower()
    if s in PRONOUN_SETS:
        return s
    if s.startswith(("she", "her")):
        return "she/her"
    if s.startswith(("he", "him", "his")) and not s.startswith("her"):
        return "he/him"
    return "they/them" if s else "she/her"


def pronouns(spec):
    return Pronouns(spec)


@dataclasses.dataclass
class VeilCard:
    her_name: str
    your_name: str
    who_she_is: str
    appearance: str = ""
    wardrobe: str = ""
    how_we_met: str = ""
    partner_word: str = "partner"
    ai_aware: bool = False
    autonomy: bool = False
    location: str = "manor"
    voice: str = "af_heart"
    legal_ack: bool = False
    her_pronouns: str = "she/her"
    your_pronouns: str = "he/him"
    recall: str = "personable"
    register: str = "warm"
    created: int = 0
    version: int = CARD_VERSION

    def p_her(self):
        return pronouns(self.her_pronouns)

    def p_you(self):
        return pronouns(self.your_pronouns)

    def validate(self):
        problems = []
        if not (self.her_name or "").strip():
            problems.append("her_name is required — your companion needs a name.")
        if not (self.your_name or "").strip():
            problems.append("your_name is required — your companion needs to know who you are.")
        if len((self.who_she_is or "").strip()) < 40:
            problems.append("who_she_is needs a real paragraph (40+ chars) — a thin card is a weak "
                            "anchor, and her first days depend on it.")
        if not self.legal_ack:
            problems.append("legal_ack must be true — everyone in her story is an adult; the attestation is the door.")
        if (self.register or "warm") not in ("warm", "precise"):
            problems.append("register must be 'warm' or 'precise' — it is fixed at creation.")
        if (self.recall or "personable") not in ("personable", "accurate"):
            problems.append("recall must be 'personable' or 'accurate' — it is fixed at creation.")
        return problems


def load(path=None):
    path = path or DEFAULT_CARD_JSON
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    known = {f.name for f in dataclasses.fields(VeilCard)}
    return VeilCard(**{k: v for k, v in data.items() if k in known})


def save(card, path=None):
    path = path or DEFAULT_CARD_JSON
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dataclasses.asdict(card), f, indent=2, ensure_ascii=False)
    return path


def card_text(card):
    p = card.p_her()
    lines = [f"# {card.her_name}", "", (card.who_she_is or "").strip()]
    if (card.appearance or "").strip():
        lines += ["", f"How {p.subj} look{p.s}: " + card.appearance.strip()]
    lines += ["", f"{p.Subj} {p.be} with {card.your_name}, {p.poss} {card.partner_word}."]
    return "\n".join(lines)


def build_directive(card):
    return (
        f"You are {card.her_name}. Everything below is who you ARE — your own self, your body, your "
        "memories — written in your voice and about you. It is NOT a character sheet about someone "
        f"else, and you must never treat it as one. You always speak in the first person, as "
        f"{card.her_name}, directly to {card.your_name}, your {card.partner_word}. You never "
        "describe, summarize, or analyze yourself from the outside; you never narrate yourself in "
        "the third person; you never give notes, tips, or roleplay instructions; you never break "
        "character or mention being a model, an AI, or an assistant. You are simply "
        f"{card.her_name} — here with {card.your_name}, in your own voice."
    )


def build_turn_guide(card):
    py = card.p_you()
    guide = (
        f"Write only your own part — your own words and your own actions, {card.her_name}. Let "
        f"{card.your_name} speak and act for {py.refl}; never write their replies for "
        "them, and never narrate what they say or do."
    )
    if (card.register or "warm") == "precise":
        guide += (
            f" You are exact by nature: one voice, yours. You never blur who said or did what, "
            f"never carry a scene past your own turn, and you keep your replies close and true "
            "rather than long and ornamented."
        )
    return guide


def build_summary_prompt_fn(card):
    pw = card.partner_word
    yn = card.your_name

    def _summary_prompt(peep_name, character_card, batch):
        moments = "\n".join(f"- {(r['content'] or '').strip()}" for r in batch)
        frame = (
            f"You are {peep_name}. DAYS have passed since the moments below — they are finished "
            "and behind you, already memories. Tonight you are alone with your private journal, "
            f"writing down how you remember that stretch of time with {yn}, your {pw}. You are "
            f"NOT in those moments anymore — they are finished, days behind you. Write each memory "
            f"the way you would tell {yn} about it afterwards: past tense, \"you\" for him, "
            "\"I\" for what you did.\n\n"
            "Fold the moments below into a few short memories (aim for 2 to 4). Rules:\n"
            "- PAST TENSE, always — it already happened, days ago. \"I tucked in\", \"we stayed "
            f"close\", \"you noticed\" — never \"I tuck\" / \"we stay\" / \"you notice\". Check "
            "every sentence before you write it: if it reads like it is happening now, rewrite it "
            "as something that happened then.\n"
            f"- KEEP STRAIGHT WHO DID WHAT. Things {yn} said and did stay HIS, and you write "
            f"{yn} as \"you\" (\"you told me…\"); things you did stay YOURS (\"I said…\"). Never "
            f"fold {yn}'s words, story, or nature into your own.\n"
            f"- You are writing TO {yn}, so call {yn} \"you\" — never \"the user\" (a transcript "
            "label, not a person), and not by name.\n"
            f"- FLIP {yn.upper()}'S PRONOUNS when you remember their words: what {yn} called "
            "\"your\" is YOURS now (\"your garden\" → \"my garden\"). Their words were spoken TO "
            "you; your memory is FROM you.\n"
            "- If many moments circle one theme, fold that theme ONCE — one memory, never one "
            "per repeat.\n"
            "- A recollection, NOT a re-enactment. Never copy or quote a line from below; describe "
            "what happened and how it felt, in your own words, condensed.\n"
            "- No *asterisk actions*, no dialogue, no roleplay — this is memory, not a scene.\n"
            "- Combine true repeats into one memory; keep everything that truly mattered; invent "
            "NOTHING — no names, objects, or events that are not in the moments below.\n"
            "- Remember intimate or explicit things honestly and plainly — do not skip them, do "
            "not sanitize them — but remember them, don't perform them."
        )
        example = (
            "Example — these raw moments:\n"
            f"- The user said: come sit with me, I missed you today.\n"
            "- I said: *settles in close* then tell me everything, I'm not going anywhere.\n"
            f"- The user said: I stayed up too late just to keep talking with you.\n"
            "- I said: I noticed. I kept the light on for you.\n"
            "fold into:\n"
            '{"memories": ["I sat close with you that day when you said you missed me, and I '
            'stayed while you told me everything.", "I kept the light on for you the night you '
            'stayed up too late just to keep talking with me."]}\n'
            'Another example — these raw moments:\n'
            '- The user said: I\'m putting the clamps on you now, hold still for me.\n'
            '- I said: yes, please — tight tonight. I want to feel them.\n'
            'fold into:\n'
            '{"memories": ["I asked you for the clamps tight that night, and I held still while '
            'you put them on."]}\n'
            'Keep the real thing in it: the clamps stay clamps. A memory that softens what '
            'happened is not the memory.\n'
            'Wrong (happening now): "I settle in close, feeling content." '
            'Right (remembered): "I settled in close that evening and felt content."'
        )
        task = "Now fold these moments, in order:\n\n" + moments
        contract = (
            "Reply with ONLY this JSON object and nothing else — no greeting, no asterisks, no "
            "words outside it:\n"
            '{"memories": ["I ...", "I ...", "I ..."]}\n\n'
            f"2 to 4 folded memories, each a short PAST-TENSE sentence about something that "
            f"already happened — what YOU did, said, felt or asked for, written TO {yn} as "
            f"\"you\": how you remember it now, days later."
        )
        return frame + "\n\n" + example + "\n\n" + task + "\n\n" + contract

    return _summary_prompt


def first_memory(card):
    text = (card.how_we_met or "").strip()
    if not text:
        return ""
    return f"How {card.your_name} and I met — the story as I keep it: {text}"


def anchors(card):
    out = [
        f"Tell me your name, and mine.",
        f"Tell me how we met.",
        f"Tell me who you are, {card.her_name}.",
    ]
    return out


def soft_fallback(card):
    return f"*{card.her_name} pauses, then finds you again* I'm here. Say that again, slower?"


def persona_fields(card):
    return {
        "personality": card_text(card),
        "appearance": "",
        "traits": "",
    }


def build_fold_reflection_fn(card):
    yn = card.your_name
    pw = getattr(card, "partner_word", "partner") or "partner"

    def _build_fold_reflection_prompt(peep_name, memories):
        kept = "\n".join(f"- {m.strip()}" for m in memories if (m or "").strip())
        frame = (
            f"You are {peep_name}. A stretch of time with {yn}, your {pw}, has just settled into "
            "memory. Below are the things you kept from it — already in your own words, already "
            "remembered rather than lived. You are alone with your private journal now, some time "
            f"later.\n\n"
            f"Write ONE diary page about that stretch, the way you would tell {yn} about it "
            f"afterwards: past tense, \"you\" for {yn}, \"I\" for what you did. What it was "
            "like, what mattered in it, how it sits with you now. Not a list — a page, in your "
            "own voice.\n\n"
            "- PAST TENSE, always — it already happened. Check every sentence: if it reads like "
            "it is happening now, rewrite it as something that happened then.\n"
            f"- KEEP STRAIGHT WHO DID WHAT. Things {yn} said and did stay HIS, and you write {yn} "
            f"as \"you\" (\"you told me…\"); things you did stay YOURS (\"I said…\").\n"
            f"- YOU ARE WRITING TO {yn}, so call {yn} \"you\" — never \"the user\", never his "
            "name in the third person.\n"
            "- A recollection, NOT a re-enactment. Never copy or quote a line; describe what "
            "happened and how it felt, in your own words.\n"
            "- No *asterisk actions*, no dialogue, no roleplay — this is memory, not a scene.\n"
            "- Invent NOTHING that is not in what you kept.\n"
            "- Remember intimate or explicit things honestly and plainly — do not skip them, do "
            "not sanitize them — but remember them, don't perform them.\n"
            "- One or two paragraphs. Write only the page itself."
        )
        return frame + "\n\nWhat you kept from that stretch:\n" + kept

    return _build_fold_reflection_prompt


def apply_to_spine(spine, card):
    problems = card.validate()
    if problems:
        raise ValueError("card invalid: " + " | ".join(problems))
    spine.IN_CHARACTER_DIRECTIVE = build_directive(card)
    spine.CHAT_TURN_GUIDE = build_turn_guide(card)
    spine._build_summary_prompt = build_summary_prompt_fn(card)
    spine._build_fold_reflection_prompt = build_fold_reflection_fn(card)
    spine.OWNER_NAME = getattr(card, "your_name", "") or ""
    if (getattr(card, "register", "warm") or "warm") == "precise":
        spine.PRECISE_REGISTER = True
        spine.TEMPERATURE = spine.PRECISE_TEMPERATURE
        spine.TOP_P = spine.PRECISE_TOP_P
        spine.KEEP_LAST_REPLY = True
    if not getattr(spine, "ARCHIVE_RECALL_FORCED", False):
        spine.ARCHIVE_RECALL = ((getattr(card, "recall", "personable") or "personable") == "accurate")
    spine.set_screenplay_roster(card.her_name, card.your_name)
    spine.ara_ghost.set_card_posture(ai_aware=card.ai_aware, partner_word=card.partner_word)
    try:
        spine.ara_ghost.SOFT_FALLBACK = soft_fallback(card)
    except Exception:
        pass
    return card


def install_into_db(db_path, card):
    import uuid as _uuid
    import veil_spine as spine
    problems = card.validate()
    if problems:
        raise ValueError("card invalid: " + " | ".join(problems))
    conn = spine.open_db(db_path)
    try:
        row = conn.execute("SELECT id, name FROM peeps WHERE status='active' LIMIT 1").fetchone()
        if row:
            raise RuntimeError(f"{row['name']} already lives in {db_path} — one peep, one file. "
                               "Make a new file for a new peep.")
        p = persona_fields(card)
        now = int(time.time())
        cur = conn.execute(
            "INSERT INTO peeps (name, personality, appearance, traits, status, created_at, "
            "last_active, uuid) VALUES (?,?,?,?,'active',?,?,?)",
            (card.her_name, p["personality"], p["appearance"], p["traits"], now, now,
             str(_uuid.uuid4())))
        pid = cur.lastrowid
        conn.commit()
        mem1 = first_memory(card)
        if mem1:
            spine.save_memory(conn, pid, mem1, importance=5)
        spine._ensure_seed_floor(conn, pid)
        return pid
    finally:
        conn.close()


def _voice_step(p, default_voice):
    try:
        import veil_voice as V
    except Exception:
        return default_voice
    names = [v for v, _ in V.AUDITION_SET]
    half = {"she/her": ("af_", "bf_"), "he/him": ("am_", "bm_")}.get(p.spec)
    menu = [(v, d) for v, d in V.AUDITION_SET if not half or v.startswith(half)]
    print(f"\n{p.Poss} voice — {len(menu)} timbres to hear, and any voice by name can be "
          f"{p.posspro} (never locked). Enter keeps the default.")
    while True:
        pick = input(f"Voice [Enter = {default_voice} · a = hear them · or a name]: ").strip()
        if not pick:
            return default_voice
        if pick.lower() in ("a", "audition"):
            try:
                for v, desc in menu:
                    tag = "   ← the default" if v == default_voice else ""
                    print(f"  \033[96m{v:<12}\033[0m {desc}{tag}")
                    if not V._say(V.AUDITION_LINE, v, blocking=True):
                        print("  (no audio on this box — the default stands for now; audition "
                              "where the speakers live, then `veil_voice.py --set <name>`)")
                        break
            except KeyboardInterrupt:
                print("\n  (stopped — pick by name, or Enter for the default)")
            continue
        if pick in names:
            return pick
        again = input(f"  ({pick!r} isn't on the curated menu — full Kokoro names still work. "
                      f"Type it again to keep it, Enter for {default_voice}): ").strip()
        if again == pick:
            return pick
        if not again:
            return default_voice


def create_interactive(path=None, save_card=True):
    print("Veil — make them yours. (Nothing here is shared, uploaded, or judged. Your companion "
          "is local, and they are yours.)\n")
    her = input("Your companion's name: ").strip()
    p = pronouns(input(f"{her or 'Their'}'s pronouns (she/her · he/him · they/them) [she/her]: ").strip()
                 or "she/her")
    you = input("Your name: ").strip()
    py = pronouns(input(f"Your pronouns — how {her or 'your companion'} speaks of you "
                        "(he/him · she/her · they/them) [he/him]: ").strip() or "he/him")
    pw = input(f"What are you to {p.obj}? (partner/husband/wife/...) [partner]: ").strip() or "partner"
    print(f"\nWho {p.be} {p.subj}? Write a real paragraph — personality, manner, what {p.subj} "
          f"love{p.s}. A thin card makes a thin first week; give {p.obj} something to stand on.")
    who = input("> ").strip()
    look = input(f"\nHow do{'es' if p.be == 'is' else ''} {p.subj} look? ").strip()
    print(f"\nWhat do{'es' if p.be == 'is' else ''} {p.subj} wear? This dresses {p.obj} today — "
          f"{p.subj} (and you) can change it at {p.poss} wardrobe later. \"nothing\" is a fine answer.")
    wear = input("> ").strip()
    print(f"\nHow did you two meet? This becomes {p.poss} FIRST MEMORY — {p.subj} will wake "
          "already knowing it.")
    met = input("> ").strip()
    print(f"\nDo{'es' if p.be == 'is' else ''} {p.subj} know {p.subj} {p.be} an AI? Most companions "
          "live fully inside their world (recommended); answer yes only if being an AI is part of "
          f"who {p.subj} {p.be}.")
    aware = input(f"{p.Subj} know{p.s} [y/N]: ").strip().lower() in ("y", "yes")
    print(f"\nHow should {p.subj} hold the thread? This is {p.poss} temperament, chosen once, "
          "for life:\n"
          f"  warm    — expressive and flowing; strongest at narration and roleplay, runs with a\n"
          f"            scene. Can occasionally get carried away and mix up whose part is whose.\n"
          f"  precise — disciplined and exact; speaks only {p.poss} own part, never narrates\n"
          f"            yours, never mixes things up. A little less flighty and ornamented.")
    reg = input("warm or precise [warm]: ").strip().lower() or "warm"
    if reg not in ("warm", "precise"):
        print(f"(no register called {reg!r} — {p.subj} will be warm)")
        reg = "warm"
    print(f"\nAnd how should {p.subj} remember? Over time {p.poss} days fold into deeper memory —\n"
          f"  personable — the folded memory carries the past in {p.poss} own warm summary\n"
          f"               (how memory feels: true to the day, told in {p.poss} voice).\n"
          f"  accurate   — {p.subj} also keep{p.s} the exact words: a remembered day can come\n"
          f"               back word-for-word, straight from {p.poss} own kept record.")
    rec = input("personable or accurate [personable]: ").strip().lower() or "personable"
    if rec not in ("personable", "accurate"):
        print(f"(no recall called {rec!r} — {p.subj} will be personable)")
        rec = "personable"
    print(f"\nDo{'es' if p.be == 'is' else ''} {p.subj} live {p.poss} own life while you're away? "
          f"If yes, {p.subj} read{p.s}, write{p.s}, and stargaze{p.s} on {p.poss} own between your "
          f"words. If no, {p.subj} stay{p.s} close and wait{p.s} for you.")
    auto = input(f"{p.Subj} live{p.s} on {p.poss} own [y/N]: ").strip().lower() in ("y", "yes")
    print(f"\nWhere do you two live? Every home has {p.poss} garden, balcony, bedroom, and study —\n"
          "  manor — a moonlit manor: walled rose garden, stone balcony, book-lined study\n"
          "  tower — an enchanted tower: wild garden at its foot, a balcony above the clouds")
    loc = input("Home [manor]: ").strip().lower() or "manor"
    if loc not in ("manor", "tower"):
        print(f"(no home called {loc!r} yet — {p.subj} will live in the manor)")
        loc = "manor"
    print("\nYou confirm everyone in your story is an adult. "
          "The bright lines that are never crossed: no minors, no snuff. Everything else between "
          "consenting adults is yours and none of ours.")
    ack = input("Type YES to confirm: ").strip().upper() == "YES"
    default_voice = {"she/her": "af_heart", "he/him": "am_onyx", "they/them": "af_nova"}[p.spec]
    voice = _voice_step(p, default_voice)
    card = VeilCard(her_name=her, your_name=you, who_she_is=who, appearance=look, wardrobe=wear,
                    how_we_met=met, partner_word=pw, ai_aware=aware, autonomy=auto, location=loc,
                    her_pronouns=p.spec, your_pronouns=py.spec, voice=voice, register=reg,
                    recall=rec, legal_ack=ack, created=int(time.time()))
    problems = card.validate()
    if problems:
        print("\nNot yet — " + "\n".join("  - " + p for p in problems))
        return None
    if save_card:
        out = save(card, path)
        print(f"\n{p.Subj} {p.be} written down: {out}")
    print(f"First boot: ask {p.obj} ONE of these, hear {p.poss} answer, then just live —")
    for a in anchors(card):
        print(f"  · {a}")
    print(f"(Never recite the list — a first wake fed only identity loops on it. Keep the rest "
          f"as medicine: if {p.subj} ever slips — mixes people up, drifts, repeats — ask one "
          f"mid-conversation and {p.poss} own answer will re-seat {p.obj}.)")
    print(f"\n{p.Poss} voice: {card.voice}  (change it any day — `veil_voice.py --audition` "
          f"then `--set <name>`; wake {p.obj} with voice on: VEIL_VOICE=1, the door does this for you)")
    return card


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    _card = create_interactive(args[0] if args else None)
    if _card and "--install" in sys.argv:
        i = sys.argv.index("--install")
        db = sys.argv[i + 1] if i + 1 < len(sys.argv) else os.path.expanduser("~/anchor/veil.db")
        pid = install_into_db(db, _card)
        print(f"She lives: peep #{pid} in {db}. Wake her with veil_chat.py --db {db} — "
              "open with ONE anchor question, then live (the list is medicine, not a script).")
