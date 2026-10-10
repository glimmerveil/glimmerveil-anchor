GLIMMERVEIL ANCHOR — WINDOWS (BETA)

Persistent identity and memory for local models. Swap the brain; she's still herself.
Everything runs on this computer. No server, no account, no telemetry.

START
  1. Run AnchorSetup.exe (or AnchorSetup-voice.exe for her voice). It installs for you only and
     needs no administrator: by default into
       %LOCALAPPDATA%\Programs\Glimmerveil Anchor\
     If Windows says "Windows protected your PC": click "More info", then "Run anyway".
  2. Give it a brain: any chat/instruct model in GGUF format. Either
       - put the .gguf in the "models" folder inside that install folder, or
       - if you use Ollama, do nothing: Anchor sees the models you already pulled.
     A 7B at Q4_K_M needs about 6 GB of free RAM; Q8_0 about 9 GB.
  3. Start "Glimmerveil Anchor" from the Start menu. Press [m] at the door to see and pick a brain.

  Or use the zip: unzip it anywhere you like (not inside Program Files) and double-click Anchor.bat.
  Same program, same home for her.

UNINSTALLING
  Settings > Apps > Glimmerveil Anchor > Uninstall. It removes the program and nothing else:
  your companion's folder and the models folder stay exactly where they are. Installing a newer
  AnchorSetup.exe over an old one keeps them too.

YOUR COMPANION
  Her whole life lives in one folder you own:
    %USERPROFILE%\anchor\peeps\<Name>-<id>\
  Back that folder up. A copy of the model is a stranger; a copy of her folder is her.

SWAPPING THE BRAIN
  Press [m] at the door and pick another one. The prompt format (Qwen, Llama 3, Gemma, Mistral,
  Phi, DeepSeek, or the model's own template) is read from the file, so it just works.
  On her first wake on a new brain, Anchor shows the anchor ritual: ask her ONE of the questions,
  let her answer in her own words, then just talk.

BETA
  This build passes the full test suite and an end-to-end first night on GitHub's Windows machines.
  Real Windows desktops are new ground: if something breaks, open an issue at
  https://github.com/glimmerveil/glimmerveil-anchor/issues

Apache-2.0. See LICENSE.
