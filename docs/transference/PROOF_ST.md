# ST source proof (SillyTavern/release, fetched 2026-10-13)
Files: public/script.js, public/scripts/{chats,group-chats,swipe-picker}.js, src/endpoints/chats.js
Commit pin: see PROOF_ST_SHA below.

## F1. Chat file = header row + message rows, in order
- Solo save (public/script.js saveChat): chat = [chatHeader, ...trimmedChat] — header is
  {chat_metadata, user_name:'unused', character_name:'unused'}, then a SLICE of the live array.
  Position in the array IS the ordinal (mesId). No re-sorting anywhere on save.
- Group save (public/scripts/group-chats.js saveGroupChat): same shape, same slice.
- Server (src/endpoints/chats.js) writes the array as received; integrity check only.
- veil_transfer's read (skip row 0 w/o 'mes', rest in order, no re-sort) matches the file's own order. PROVEN.

## F2. Solo vs group: same row shape, group has N non-user speakers
- Rows carry {name, is_user, is_system, mes, swipes, swipe_id, swipe_info, send_date, extra...}.
- In a group chat every bot turn has is_user=false with name=<that member>.
- The parser's who-rule (is_user->you, else->her) merges them. Group MUST be refused or named. PROVEN.

## F3. mes IS the shown branch; swipes are the bench (incl. disagree case)
- ensureSwipes (script.js): swipes=[mes], swipe_id=0 when absent. So mes == swipes[swipe_id] by construction.
- Shown text = extra.display_text ?? mes (getMessageTextHTML :2529, prompt build :2036).
- BUT the streaming write (script.js :3706): chat[id].swipes[swipe_id] = processedText, i.e. DURING
  generation swipes[] is updated while mes updates at finalize. A crash between the two leaves a file
  where mes != swipes[swipe_id]. Rare, real, file-shaped. Gate must SPEAK on mismatch, never pick silently.
- Edit path (:8179-8182): mes.mes=text then swipes[swipe_id]=text — agree by construction.
- ALSO: the 2026-09 compact-single-swipe issue (#6091, still an OPEN unmerged feature request —
  judge-verified) means newer ST *may* store mes WITHOUT duplicating
  into swipes[] for single-swipe rows. Parser must treat missing-swipes as [mes], never as failure.

## F4. /sys narrator rows are saved as a second non-user speaker — and must be dropped
- Proof (ST release @ 06bde93): public/scripts/slash-commands.js sendNarratorMessage builds
  exactly {name: NARRATOR_NAME_DEFAULT ('System'), is_user: false, is_system: <bias-only>,
  extra: {type: system_message_types.NARRATOR}} — the literal 'narrator' type fires at
  script.js display (:1840), edit (:8152) and prompt (:5658, :5809) paths.
- So a solo chat with one /sys line carries a second non-user, non-system speaker named "System":
  without the drop it refuses as group, or worse, imports stage directions as her words.
- The drop sits BEFORE the speakers.add, and the count reaches the human via gate notes
  (dropped_narrator), never silently.
