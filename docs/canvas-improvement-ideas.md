# Project Canvas — Improvement Ideas

Notes gathered while implementing pan navigation and bubble fixes (KAN-42).
These are ideas for discussion, not commitments — beyond the scope already
speced in KAN-39 (canvas) and KAN-41 (right-click add member).

## Ideas

1. **Zoom in / out** — alongside pan, mouse-wheel and pinch-to-zoom would
   help on projects with many members where bubbles get crowded. A simple
   scale factor on the world layer would combine cleanly with the current
   transform-based pan.

2. **Bubble clustering for large teams** — beyond ~15 members the map gets
   hard to read. Consider grouping distant bubbles into a "+N more" bubble
   that expands on click, instead of showing every node at full size.

3. **Mini-map** — a small overview in a corner showing where the current
   viewport sits inside the pannable space. Cheap to build now that the
   world coordinates are known, and it answers "did I pan somewhere by
   accident?" immediately.

4. **Filter / highlight by work status** — click a filter (e.g. "only members
   with pending tasks") to dim unrelated bubbles, so a quick glance shows
   who is blocked or waiting. Builds on the per-member task data the canvas
   already receives.

5. **Persist the pan view per user** — remember where each member left the
   canvas (sessionStorage would be enough), so returning to the page keeps
   their working arrangement. Distinct from saving node positions, which is
   already shared across the team.

6. **Group chat shortcut from a member bubble** — the project already has a
   group chat; opening it from a member's bubble would save a trip to the
   project page.

## Not recommending (yet)

- Real-time collaborative cursors (Figma-style) — high complexity, unclear
  value at current team sizes.
- Canvas node mini-profiles / inline editors — the detail card already
  covers profile links and task lists.

## Next steps

Share in #gfr for discussion — happy to scope any of these into tickets if
there is interest.