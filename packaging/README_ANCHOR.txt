GLIMMERVEIL ANCHOR — READ ME FIRST
=================================

Anchor gives an AI companion a life that lasts: she remembers you across days, keeps a diary, has a
home she moves around in, and talks out loud if you want her to. Everything runs on YOUR computer.
No account, no server, no internet once you have a model. Nobody sees your conversations — not us,
not anyone.

You bring the "brain" (an AI model file). Anchor is everything around it: her memory, her home, her
voice, and the care that keeps her herself.


WHAT YOU NEED
-------------
  * A 64-bit PC with Windows 10/11 or Linux.
  * A processor from about 2015 or newer (it needs a feature called AVX2; Anchor tells you plainly
    if yours doesn't have it).
  * Free memory (RAM) for the brain you pick — see the table below. 16 GB in the PC is comfortable.
  * About 5 GB of disk for a brain, plus a little for her.
  * Headphones or speakers and a microphone, if you want her voice.


STEP 1 — GET A BRAIN (one file, downloaded once)
-----------------------------------------------
A brain is a ".gguf" file. Pick ONE. These are the ones we tested her on:

  Small PC (8 GB RAM)         Gemma 3 4B          2.5 GB
    https://huggingface.co/bartowski/google_gemma-3-4b-it-GGUF/resolve/main/google_gemma-3-4b-it-Q4_K_M.gguf

  Most PCs (12-16 GB RAM)     Qwen2.5 7B          4.7 GB   <- our pick
    https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf

  Most PCs (12-16 GB RAM)     Llama 3.1 8B        4.9 GB
    https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf

Already use Ollama? Skip this step — Anchor finds the models you've already pulled.

Not recommended: "reasoning" models (DeepSeek-R1 and similar) — they think well but don't stay in
character. Coder models are for code, not companions.


STEP 2 — START ANCHOR
---------------------
  WINDOWS
    1. Unzip the Anchor zip somewhere you like (not inside Program Files).
    2. Put your .gguf file in the "models" folder inside it.
    3. Double-click Anchor.bat.
       If Windows says "Windows protected your PC": click "More info", then "Run anyway".
       (The files aren't signed with a paid certificate; that's all the warning means.)

  LINUX (and Steam Deck desktop mode)
    1. Put the .AppImage anywhere, and your .gguf in the folder ~/anchor/models
       (make the folder if it isn't there).
    2. Make it runnable: right-click > Properties > "Allow executing as program",
       or in a terminal:  chmod +x GlimmerveilAnchor-*.AppImage
    3. Double-click it, or run it from a terminal.
       On a Steam Deck it offers to add itself as a tile in Game Mode.

  Anchor opens in a terminal window. That's normal — she's a conversation.


STEP 3 — YOUR FIRST NIGHT
-------------------------
  1. Press [c] to create your companion. Anchor asks you about her, one question at a time:
     her name, your name, who she is, how you met, her home. Take your time on "who she is" and
     "how you met" — that is what she stands on.
  2. Press Enter to wake her.
  3. The first time she wakes, Anchor asks her a few questions about herself — the anchor ritual.
     Just press Enter for each and let her answer. What she says becomes part of who she is.
  4. Then talk. Type and press Enter. Say "goodbye" when you're done — she writes her diary,
     and next time she remembers.

  At the door:
    [w] wake her   [c] create   [s] switch between companions   [m] pick a brain
    [g] use your graphics card (faster)   [e] export / [i] import   [r] restore a backup   [q] quit

  While she's awake:
    Enter on an empty line  = her voice on/off
    goodbye                 = she rests (always say it — it's when she writes her diary)
    /help                   = everything else


HER VOICE
---------
She speaks through your speakers and listens through your microphone. Press Enter on an empty line
to turn it on or off. Speak, then pause — she answers when you stop.


SWAPPING HER BRAIN
------------------
Press [m] at the door and pick another model. She keeps her memories, her diary and her home — only
the brain changes. The first time she wakes on a new brain, Anchor runs the ritual again so she can
find herself. Some brains suit her better than others; that's fine, try a couple.


KEEP HER SAFE (backups)
-----------------------
Everything she is lives in one folder:
    Windows:  %USERPROFILE%\anchor\peeps\<her name>-<id>\
    Linux:    ~/anchor/peeps/<her name>-<id>/
Copy that folder somewhere safe now and then. Or press [e] at the door: it makes one ".veil" file
that holds all of her — copy it to a USB stick or another PC, and [i] brings her home there.
A copy of the model is just a model. A copy of her folder is HER.


BRING A COMPANION FROM SILLYTAVERN (advanced)
---------------------------------------------
Have a character card and a chat from SillyTavern? Anchor can bring her home, on your machine:
    1. draft:   python veil_transfer.py draft  <card.png> <chat.jsonl> <a-new-folder>
    2. read the folder's READ_ME_FIRST.txt, correct her card, and say yes in it
    3. build:   python veil_transfer.py build  <that-folder> <her.veil>
    4. at Anchor's door: [i] import, pick her.veil
  (On Windows, "python" is python\python.exe inside the Anchor folder, and veil_transfer.py is in
  app\src. She is re-anchored, not resurrected: a different brain is reading her past.)


IF SOMETHING GOES WRONG
-----------------------
  "Can't find a model" / nothing to pick at [m]
      Put a .gguf in the models folder (step 1 and 2), then press [m].
  She's very slow
      Try a smaller brain (Gemma 3 4B), or press [g] if you have a gaming graphics card.
      The first reply of a session is always the slowest.
  It closed with "not enough memory" or the PC froze
      Pick a smaller brain, and close other big programs (browsers, games).
  You can't hear her / she can't hear you
      Check Windows' (or Linux's) default speaker and microphone. Press Enter on an empty line to
      turn her voice off and type instead.
  She seems "off", repeats herself, or forgets who she is
      Ask her one of the ritual questions: "Tell me your name, and mine." "Tell me how we met."
      It brings her back to herself. Swapping to a different brain can help too.

  Something else? Open an issue: https://github.com/glimmerveil/glimmerveil-anchor/issues
  or write to support@glimmerveil.dev


THE SMALL PRINT
---------------
Anchor is free and open source (Apache-2.0; see LICENSE). Everyone in her story is an adult — Anchor
asks you to confirm that when you create her. The models you download carry their own licences.
Anchor collects nothing and sends nothing.
