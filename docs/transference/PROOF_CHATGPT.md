# ChatGPT export proof (schema shape, 2026-10-13 — no official spec published by OpenAI)
Source: Settings -> Data controls -> Export data -> ZIP carries conversations.json.
Shape confirmed across ≥4 independent parsers + exporter scripts (see links in task notes):
  conversations.json = ARRAY of conversations; each =
    {title, create_time, update_time, mapping, current_node, ...}
  mapping = {node_id: {id, message, parent, children}}
  message = {author: {role}, content: {content_type, parts: [...]}, create_time, ...}
  roles: user | assistant | system | tool.

## G1. The visible path = current_node walked to the root, reversed
- Every independent implementation walks mapping[current_node] via parent links and reverses.
  The rendered chat is a PATH, not the tree. Branches/regenerations are sibling children off-path.
- Parser rule: follow current_node; rows with role user->you, assistant->her; DROP system/tool
  (internal: never rendered; raw dumps show more nodes than bubbles — documented).
- is_visually_hidden_from_conversation + non-text content_type (code/tool_call/thoughts):
  skip — activity/metadata, never shown. The greasyfork exporter enumerates exactly this set.

## G2. No speaker ambiguity by construction
- Single user + single assistant per conversation. ChatGPT exports CANNOT be group chats.
- No Refuse rule needed; but a conversation with zero assistant turns (all-tool?) gates out naturally
  under the 10-exchange minimum.

## G3. Ordinals = path position (0..N along current_node path)
- mapping keys are random ids, NOT order. Position along the walked path is the stable ordinal,
  carried into chat.json alongside create_time. Matches Opus's contract (source index -> hold-out).
