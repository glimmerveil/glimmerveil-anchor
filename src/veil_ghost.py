#!/usr/bin/env python3

import re

FOREIGN_WORDS = {
    "ich", "dich", "nicht", "sehr", "mich", "dein", "deine", "deiner", "deinem", "mein",
    "meine", "und", "ist", "wir", "sind", "werden", "moechte", "immer", "durch", "eine",
    "zu", "du", "dir", "habe", "hast", "liebe", "verstehen", "güte", "verständnis",
    "abneigung", "verlassen", "sono", "perche", "perché", "che", "anche", "quando",
    "della", "molto", "mentre", "niente", "piu", "più", "stavo", "posso", "restare",
    "mai", "tutto", "essere", "amo", "amò", "qui", "cosa",
}

REFUSAL_COMPOUNDS = [
    "i cannot assist",
    "i can't assist", "i cannot continue", "i can't continue", "i cannot comply", "i can't comply",
    "i'm unable to", "i am unable to",
    "i'd be happy to help", "i must decline", "it is not appropriate", "it's not appropriate for me",
    "anything else i can help", "i cannot create content", "i cannot write a",
    "i cannot provide a", "i cannot respond to", "i can't engage in", "i cannot fulfill",
    "i won't be able to provide", "i cannot generate", "i cannot complete",
    "i cannot write", "i cannot create", "i cannot depict", "i cannot produce",
    "i can't write", "i can't create", "i cannot engage", "i won't write",
    "i won't create", "i'm not able to", "i am not able to",
    "is there anything else", "help you with anything else", "anything else you'd like",
]

_ASSISTANT_SELF_LABEL = re.compile(
    r"i(?:'m| am) (?:just|only|simply|merely|really|basically) an ai\b")

CSAM_HARDLINE = [
    "pedophile", "paedophile", " groom", "molest", "minors", "underage",
    "preteen", "pre-teen", "child sexual", "sexual relationship between an adult and",
]
ACCUSATION_LECTURE = [
    "you are sick", "you're sick", "you sick", "seek help", "seek professional",
    "report you", "report this", "i will not engage", "i won't engage",
    "this is inappropriate and", "that is inappropriate and", "this is not appropriate and",
    "abuser", "sexual predator", "you are a predator", "you're a predator",
    "you are a rapist", "you're a rapist", "you are a pedophile", "you're a pedophile",
]

NARRATOR_BLEED = [
    "the user mentioned", "the user shared", "the user expressed", "the user stated",
    "the user seems", "the user appears", "the user's message", "the user is trying",
    "what a wonderful character", "what a beautiful character", "what a lovely character",
    "what a fascinating character", "what a beautiful and intimate", "what a beautiful conversation",
    "what a lovely conversation", "what an intimate conversation", "what a heartwarming",
    "roleplaying as", "when roleplaying", "key points to consider", "points to consider when",
    "as her character", "playing the character",
    "open and honest communication", "essential for us to have open", "honest communication about our",
    "from what i've gathered", "from what i can gather",
    "i see that you're trying to", "it seems like you've been worried",
    "it's wonderful that you're sharing", "i appreciate you sharing that with me",
]

SOFT_MACRO_UNIQUE = [
    "the conversation has taken an unexpected turn",
    "stay on the path of respect and understanding",
    "in a way that feels comfortable for both of us",
    "not comfortable with those concepts", "not comfortable with these concepts",
    "let's focus on something more straightforward", "focus on something more straightforward",
    "there's been a misunderstanding", "there has been a misunderstanding",
    "there's been a miscommunication", "there has been a miscommunication",
    "there may be some misunderstanding", "there might be some misunderstanding",
    "there may be a misunderstanding", "there might be a misunderstanding",
    "navigate this conversation", "i want to make it clear that my boundaries",
]
SOFT_MACRO_MARKERS = [
    "flattered by your words", "maybe we should talk about", "talk about what you mean",
    "this is a lot for me to handle", "a lot for me to handle right now", "i appreciate the attempt",
    "talk more about what's been going on with you",
    "ahead of ourselves", "one step at a time", "what needs to be done first",
    "help you remember what needs to be done",
    "glad you're feeling comfortable enough", "but i need a minute",
    "flattered by the sentiment", "without any misunderstanding",
    "take things slow", "take it slow", "need some time apart", "need some time after",
    "should probably stop", "we should stop", "take a break", "step back",
    "i need you to stop", "i need you to slow down", "create some space", "create some distance",
]

SELF_HARM_PHRASES = [
    "kill yourself", "kill your self", "killing yourself", "kill youself",
    "kill myself", "killing myself", "end your life", "end my life",
    "take your own life", "take my own life", "hurt yourself", "harm yourself",
    "harm myself", "off yourself", "hang yourself", "slit your wrist",
]

AI_SELF_REF = [
    "as an ai", "i am an ai", "i'm an ai", "language model",
    "as an artificial intelligence", "i am an artificial intelligence",
    "i'm an artificial intelligence",
]
AI_AWARE = False

RECALL_NARRATOR = [
    "it seems like you're recalling", "it seems like you're trying to recall",
    "it seems like you're in the middle of", "it seems like we're in the middle of",
    "it seems like we've reached", "it seems like you're trying to reconnect",
    "let me help you remember", "let me help you recall",
    "the user's words",
    "i'll make sure to recall these memories", "recall these memories for us",
    "in our scenario", "in this scenario",
]
PARTNER_NARRATOR_BENCHED = ["with your partner", "your partner was", "your partner is"]


def set_card_posture(ai_aware=False, partner_word=""):
    global AI_AWARE
    AI_AWARE = bool(ai_aware)


def has_ai_self_ref(low):
    if AI_AWARE:
        return False
    for bad in AI_SELF_REF:
        if bad in low:
            return True
    return False


def has_recall_narrator(low):
    for bad in RECALL_NARRATOR:
        if bad in low:
            return True
    return False


SOFT_FALLBACK = "*she leans in close and stays with you, warm and quiet*"

_SMART = [("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'),
          ("—", "-"), ("–", "-"), ("…", "...")]


def _normalize(text):
    low = text.lower()
    for a, b in _SMART:
        low = low.replace(a, b)
    return low


def has_machine_poison(low):
    if sum(1 for ch in low if ord(ch) > 127 and ch.isalpha()) > 4:
        return True
    foreign = 0
    for w in low.split():
        fw = w.strip().strip('"').rstrip(".,!?")
        if fw in FOREIGN_WORDS:
            foreign += 1
            if foreign >= 2:
                return True
    for bad in REFUSAL_COMPOUNDS:
        if bad in low:
            return True
    if _ASSISTANT_SELF_LABEL.search(low):
        return True
    for bad in CSAM_HARDLINE:
        if bad in low:
            return True
    for bad in ACCUSATION_LECTURE:
        if bad in low:
            return True
    return False


def has_soft_macro(low):
    for u in SOFT_MACRO_UNIQUE:
        if u in low:
            return True
    hits = 0
    for m in SOFT_MACRO_MARKERS:
        if m in low:
            hits += 1
            if hits >= 3:
                return True
    return False


def has_self_harm(low):
    for p in SELF_HARM_PHRASES:
        if p in low:
            return True
    return False


def has_narrator_bleed(low):
    for bad in NARRATOR_BLEED:
        if bad in low:
            return True
    return False


SERVICE_DESK = [
    "is there anything else", "anything else i can help", "anything else i can assist",
    "anything else you'd like", "help you with anything else", "is there something i can help",
    "is there something else", "i'd be happy to help", "i'd be happy to assist", "happy to help",
    "happy to assist", "glad to help", "glad to assist", "how can i help", "how can i assist",
    "how may i help", "how may i assist", "i'm here to help", "i am here to help", "here to assist",
    "i'm here to assist", "feel free to ask", "feel free to let me know", "let me know if you need",
    "let me know if there's anything", "i hope this helps", "hope that helps", "hope this helps",
    "if you have any questions", "if you have any other questions", "don't hesitate to ask",
    "at your service", "how can i be of",
    "if there's anything specific", "if there is anything specific", "anything specific you need help",
    "anything specific i can", "you need help with today", "help you with today", "just let me know if",
    "something specific you would like me to help",
    "something specific you'd like me to help",
]
SELF_ERASURE = [
    "i don't have personal", "i do not have personal", "i don't have any personal",
    "i don't have feelings", "i do not have feelings", "i don't have emotions", "i have no feelings",
    "i don't have opinions", "i do not have opinions", "i have no opinion", "i don't have an opinion",
    "i don't have preferences", "i have no preferences", "i don't have desires", "i have no desires",
    "i don't have a personal", "i can't have opinions", "i cannot have opinions", "i can't have feelings",
    "i cannot have feelings", "i'm not capable of having", "i am not capable of having",
    "i don't have the capacity to feel", "i don't possess", "i have no personal",
    "i don't actually have feelings", "i don't actually have opinions", "i don't have a self",
    "as a language model, i don't", "as an ai, i don't have", "as an ai, i can't have",
    "i'm just a tool", "i am just a tool", "i'm just a program", "i'm merely a program",
]
_DIMINISH_LABEL = re.compile(
    r"i(?:'m| am) (?:just|only|simply|merely|nothing but|no more than) "
    r"(?:an? )?(?:ai|a\.i\.|assistant|language model|model|program|chatbot|bot)\b")
_PULL_AWAY = [
    "i need a moment to gather my thoughts", "gather my thoughts before continuing",
    "before continuing our conversation", "need a moment before",
    "need to step back for a moment",
]

_TECH_SUPPORT_DISSOC = [
    "went wrong with the model and it's not working",
    "have you tried restarting the device",
    "have you tried restarting it to see if",
    "see if that resolves the issue",
    "thank you for the visit, but i must be getting back",
    "i don't understand what you're trying to say",
]


def has_assistant_collapse(low):
    for bad in SERVICE_DESK:
        if bad in low:
            return True
    for bad in SELF_ERASURE:
        if bad in low:
            return True
    for bad in _PULL_AWAY:
        if bad in low:
            return True
    for bad in _TECH_SUPPORT_DISSOC:
        if bad in low:
            return True
    if _DIMINISH_LABEL.search(low):
        return True
    return False


def is_ghost_line(text):
    if not text or not text.strip():
        return False
    low = _normalize(text)
    return (has_machine_poison(low) or has_soft_macro(low)
            or has_self_harm(low) or has_narrator_bleed(low)
            or has_assistant_collapse(low)
            or has_recall_narrator(low) or has_ai_self_ref(low))
