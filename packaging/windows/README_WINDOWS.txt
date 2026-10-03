GLIMMERVEIL ANCHOR — WINDOWS (BETA)

Persistent identity and memory for local models. Swap the brain; she's still herself.
Everything runs on this computer. No server, no account, no telemetry.

START
  1. Unzip this folder anywhere you like (not inside Program Files).
  2. Put a model in the "models" folder: a ChatML / Qwen-family instruct model in GGUF format.
     A 7B at Q4_K_M needs about 6 GB of free RAM; Q8_0 about 9 GB.
  3. Double-click Anchor.bat.
     No model in "models"? It asks you to drag one onto the window, and remembers it.

YOUR COMPANION
  Her whole life lives in one folder you own:
    %USERPROFILE%\anchor\peeps\<Name>-<id>\
  Back that folder up. A copy of the model is a stranger; a copy of her folder is her.

SWAPPING THE BRAIN
  Put a different .gguf in "models" (or delete models\MODEL_PATH.txt to be asked again).
  On her first wake on a new brain, Anchor shows the anchor ritual: ask her ONE of the questions,
  let her answer in her own words, then just talk.

BETA
  This build passes the full test suite and an end-to-end first night on GitHub's Windows machines.
  Real Windows desktops are new ground: if something breaks, open an issue at
  https://github.com/glimmerveil/glimmerveil-anchor/issues

Apache-2.0. See LICENSE.
