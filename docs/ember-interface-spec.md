# Ember Interface Spec, version 1

**Status:** written on 2026-10-30 from the design session. `PRODUCT.md` and `DESIGN.md` are approved by the founder. Undo is decided (option A) and its grouping is decided (Option 2, a group id column). The founder confirmed the two rule amendments on 2026-10-30 (section 12.3). The close confirmation is still open (12.7). Nothing here is built.
**Destination of this spec:** decide the interface well enough that a builder can start without guessing. It is not a build.
**Words:** this spec uses the words in `GLOSSARY.md` (knowledge base, item, proposal, confirm, link, source, status, ledger, sweep, backup, export).
**Marks:** *Fact* means read from a named file or page. *Inference* means my judgment. *Open* means undecided.

---

## Problem Statement

A person on a project team who does not write code wants to keep what the project decided, assumed, found and asked. Ember does that job, but today it is a terminal tool. To use it they must:

- learn 18 commands (`docs/commands.md` lists 17 entries because it groups `set-validated` and `clear-validated` under one heading),
- remember flags such as `--item N`, `--link N`, `--reason`, `--field` and `--since` (which needs an ISO-8601 time with a UTC offset),
- find and keep item numbers in their head,
- get an AI service key with a script, and load it into the shell before a real run,
- install an extra package before `relate` works.

For this person the first five minutes fail before Ember shows its value. The founder is the only confirmed user today. No other person has been asked or observed (*Open*).

## Solution

A desktop app with two modes: a **full window** and a small **quick popup** opened by a keyboard shortcut. The app does every job that the 18 commands do, with fewer things to remember than the terminal needs. It runs the same Ember code, so it can never do something the terminal cannot.

The full window has a sidebar of jobs: **Home**, **Add**, **Look up**, **Link items**, **Fix and close**, **Clean up**, **Keep safe**, and **Settings**. A first-run screen sets up the knowledge base file and the AI connection.

Three ideas make it Ember's own:
1. **Heat.** Every item shows how hot it is: a full dot is Active, a half dot is Challenged, an empty ring is Closed. A mark settles when an item's status changes.
2. **Provenance.** Selecting an item shows where it came from and what challenged or replaced it.
3. **Nothing is deleted.** The words are Reject, Close and Replaced by. Never "Delete". Every change shows in the ledger.

The look follows `DESIGN.md` (approved): Ledger Page (light) and Soot (dark) colours, Atkinson Hyperlegible type, a seven-step spacing scale.

---

## User Stories

**First run**

1. As a new user, I want a setup screen that opens the first time, so that I am not dropped into an empty window.
2. As a new user, I want to see all three steps and how far along I am, so that I know it takes about two minutes.
3. As a new user, I want to choose where my knowledge base file lives, with a sensible default, so that I do not have to type a path I do not understand.
4. As a new user, I want one sentence saying what the file holds (items, links and the ledger), so that I know what I am creating.
5. As a new user, I want to paste my AI key and test it, so that I know it works before I rely on it.
6. As a new user, I want a plain explanation of what a key is and where text goes, so that I can decide whether to connect.
7. As a new user, I want to skip the key and still use the other jobs, so that I can look around first.
8. As a new user, I want a clear message when a key is empty, too short or refused, so that I know what to fix.
9. As a new user, I want my first action to be "Add your first text", so that I reach value in one click.

**Home**

10. As a user, I want Home to tell me first what needs attention, so that I do not search for it.
11. As a user, I want to see how many items are Active, Challenged and Closed, and the total, so that I know the state at a glance.
12. As a user, I want the counts to match my items exactly, so that I can trust the numbers.
13. As a user, I want the latest ledger entries on Home, so that I see what changed recently.
14. As a user, I want a main "Add text" button on Home, so that my most frequent job is one click away.
15. As a user, I want a button on the attention message that takes me to the fix or the sweep, so that I can act on what I read.

**Add**

16. As a user, I want to paste text and press one button, so that Ember proposes items from it.
17. As a user, I want to be told that my text is kept word for word as a source and is sent to an AI service, so that I know where it goes.
18. As a user, I want to see one proposal at a time with its type, statement and the quote from my text, so that I can judge it.
19. As a user, I want a warning when a proposal looks similar to an existing item, so that I do not save duplicates by accident.
20. As a user, I want to confirm, reject or edit each proposal, so that only what I approve is saved.
21. As a user, I want to change a proposal's type and statement before confirming, so that I can correct the AI.
22. As a user, I want to stop part-way, so that I can leave without confirming the rest.
23. As a user, I want Return to confirm and Esc to stop, so that I can work with the keyboard.
24. As a user, I want a "Saved so far" list while I work, so that I see each confirm take effect.
25. As a user, I want a summary at the end (how many confirmed, how many rejected), so that I know what happened.
26. As a user, I want a one-click path from the summary to Link items, so that I can connect the new items.
27. As a user, I want a clear message when the AI service cannot be reached, saying my text is saved and nothing was created, with a retry, so that I do not lose work.
28. As a user, I want a clear message when nothing can be proposed from my text, so that I do not think the app is broken.
29. As a user without a key, I want Add to tell me it needs the connection and take me to the setting, so that I can fix it.

**Look up**

30. As a user, I want a search box with a visible label, so that I know what it does.
31. As a user, I want to filter by status and by type, so that I can narrow a long list.
32. As a user, I want to see how many items match out of the total, so that I know the scope of my search.
33. As a user, I want to see each item's number, type, text and heat mark in a table, so that I can scan it.
34. As a user, I want to select an item to see where it came from, so that I understand why it exists.
35. As a user, I want the item's source, its rationale and its reasons, so that I can answer "why was this decided?".
36. As a user, I want to see what challenged, replaced, answered or supports an item, with the other item's heat mark, so that I see its history in one place.
37. As a user, I want a Ledger tab with every change in order, so that I can see the full record.
38. As a user, I want to filter the ledger to one item or to changes since a date, and to page through it, so that a long ledger stays usable.
39. As a user, I want a message and a "Clear filters" button when nothing matches, so that I can recover.
40. As a user, I want an empty knowledge base to say "No items yet" with a way to add, so that it points me forward.
41. As a user, I want a loading state and an error state with a retry, so that I know what is happening.

**Link items**

42. As a user, I want Ember to propose how items relate (supports, contradicts, supersedes, answers, depends on), so that I do not link by hand.
43. As a user, I want to see both items and the relationship in one proposal, so that I can judge it.
44. As a user, I want to confirm, skip or reject each link proposal, so that I stay in control.
45. As a user, I want to be told the first run may take minutes while a language model downloads, so that I do not think it has frozen.
46. As a user, I want a clear message when no unrelated items are left, so that I know I am done.
47. As a user, I want a summary of links confirmed and skipped, so that I know what changed.
48. As a user without a key, I want the same "needs the connection" path as Add, so that the product behaves consistently.

**Fix and close**

49. As a user, I want to pick an item from a list instead of typing its number, so that I never need to know ids.
50. As a user, I want to mark an item Challenged or Active, so that I can flag or clear a doubt.
51. As a user, I want the status buttons to be off for a Closed item, with the reason shown, so that I understand why.
52. As a user, I want to mark an assumption verified or clear that mark, so that I can record my checking.
53. As a user, I want "verified" to be unavailable on other item types, with the reason shown, so that the rule is clear.
54. As a user, I want to edit the rationale of a Decision and the source of a Finding, so that I can fix those two fields.
55. As a user, I want other edits to be unavailable with a reason, so that I do not try to change what Ember forbids.
56. As a user, I want to preview closing an item before it happens, so that I see what else changes.
57. As a user, I want the preview to say how many dependent items become Challenged, and which, so that I can judge the effect.
58. As a user, I want to choose a close reason (invalidated or expired), so that the record says why.
59. As a user, I want a final confirmation that names the item and offers Cancel, so that I cannot close the wrong item.
60. As a user, I want to remove a link, with the link marked Rejected and never deleted, so that history stays complete.
61. As a user, I want to undo a replacement (supersedes) and get the older item back as Active, so that I can reverse a wrong call.
62. As a user, I want each change confirmed with a plain sentence, so that I know it worked.

**Clean up**

63. As a user, I want a sweep to update statuses by fixed rules, so that my items stay in line with their links.
64. As a user, I want to preview the sweep as a table of which item becomes what and why, so that nothing surprises me.
65. As a user, I want Apply to stay off until I have previewed, so that I cannot apply blind.
66. As a user, I want Apply to say how many changes it will make, so that I know the size of it.
67. As a user, I want to see the changed items with their new heat marks after applying, so that I see the result.
68. As a user, I want a count badge on Clean up only when changes are pending, so that the badge means something.
69. As a user, I want a message when nothing needs updating, so that I know all is well.

**Keep safe**

70. As a user, I want to back up with one button and choose where the file goes, so that I can protect my work.
71. As a user, I want to see the result with the number of items and the file location, so that I know it is verified.
72. As a user, I want the backup to refuse to overwrite my knowledge base file itself, so that I cannot ruin it.
73. As a user, I want to export a plain text file any editor can read, so that my knowledge outlives Ember.
74. As a user, I want a clear statement that an export cannot be restored into Ember, so that I do not confuse it with a backup.
75. As a user, I want a health check that reports problems in plain words, so that I can trust my file.
76. As a user, I want to open a different knowledge base file, including a backup, so that I can restore (restore is not a command by design).
77. As a user, I want a clear message when a backup or export fails, so that I know my file is unchanged.

**Settings**

78. As a user, I want Settings in panes (Appearance, Quick popup, Menu, AI connection), so that related choices sit together.
79. As a user, I want Settings to open with Command+Comma on a Mac and Ctrl+Comma elsewhere, so that I can reach it fast.
80. As a user, I want the window title to name the open pane and the last pane remembered, so that I keep my place.
81. As a user, I want every change to save itself with a quiet "Saved", so that I never look for a Save button.
82. As a user, I want to set text size from Small to Largest (200% of Default), so that I can read comfortably.
83. As a user, I want spacing to grow with the text, so that large text does not look cramped.
84. As a user, I want Light and Dark colours, so that I can pick what suits my room.
85. As a user, I want to change the quick popup shortcut and where it appears, so that it suits how I work.
86. As a user, I want a warning when my shortcut uses Control on a Mac, uses no modifier, or is a standard Mac shortcut, so that I avoid a bad choice.
87. As a user, I want to hide and reorder jobs in the sidebar, so that I keep it short.
88. As a user, I want Home and Settings to always stay in the sidebar, so that I cannot lose my way.
89. As a user, I want to replace or remove my AI key, with the remove button clearly marked as careful, so that I control my connection.

**Quick popup**

90. As a user, I want a shortcut that opens a small window from any program, so that I can capture a note without switching.
91. As a user, I want the popup to do only Add, so that it stays quick.
92. As a user, I want the same proposal buttons and keys as the full window, so that I do not relearn.
93. As a user, I want a link from the popup to the full window, so that I can do other jobs.
94. As a user, I want a message in the popup when setup or the key is missing, with a path to fix it, so that it never fails silently.
95. As a user, if the shortcut does not work on my system, I want a tray icon I can click instead, so that I still reach the popup.

**Keyboard, accessibility and states**

96. As a keyboard user, I want every control reachable and operable without a mouse, with a visible focus ring, so that I am not locked out.
97. As a user with low vision, I want contrast of at least 4.5:1 for text in both themes, so that I can read it.
98. As a user who cannot rely on colour, I want status shown by shape as well as colour, so that I can tell items apart.
99. As a user sensitive to motion, I want all movement off when my system asks for reduced motion, so that I am comfortable.
100. As a screen reader user, I want every control and mark to have a name, so that I can use the app.
101. As a user, I want every screen to have loading, empty and error states, so that the app never looks blank or broken.
102. As a user, I want errors to say what failed and what to do next, with the error code available on request, so that I can act or report it.
103. As a user, I want disabled controls to say why they are disabled, so that I am never guessing.
104. As a user, I want nothing to animate except a status mark settling at the moment of change, so that the app stays calm.

**Undo and redo**

111. As a user, I want to undo my last change, so that a mistake costs me one click.
112. As a user, I want to redo what I undid, so that I can change my mind again.
113. As a user, I want the button and menu item to say what will be undone, such as "Undo Close item 3", so that I can predict the result.
114. As a user, I want Undo in the Edit menu, on the Fix and close screen, and on Command+Z or Ctrl+Z, so that I find it where I expect.
115. As a user, I want undoing a close to also undo the items that close challenged, so that one undo restores everything that one action changed.
116. As a user, I want Undo to add a line to the ledger and never erase one, so that the record stays complete.
117. As a user, I want to undo several times in a row, newest first, so that I can step back through my changes.
118. As a user, I want a plain message when an undo is refused because something changed since, so that I understand why it did not work.
119. As a user, I want to know that adding text, confirming links and applying a sweep are not undone by Undo, and how to reverse each (close the item, remove the link), so that I am not surprised.
120. As a user, I want undoing a status change to restore the item's earlier protection from the next sweep, so that the sweep behaves as it did before my change.
121. As a terminal user, I want `undo` and `redo` commands with a `--dry-run`, so that the terminal can do what the window does.
122. As a user, I want the Look up ledger to show "Undone" and "Redone" in plain words, so that I can read what happened.
123. As a user, I want changes made before Undo existed to say they cannot be undone, because they carry no group id, so that I am not told something false.

**Founder and builder**

105. As the founder, I want the interface to call the same commands as the terminal, so that there is one set of rules.
106. As the founder, I want tests at the command layer, so that the interface cannot drift from the engine.
107. As the founder, I want the app to make no network request except to the AI service the user chose, so that Ember stays local-first.
108. As the founder, I want fonts bundled with their licence text, so that I meet the font licence.
109. As the founder, I want Windows and macOS builds checked automatically for launch, so that I know they start even though I cannot test them by hand.
110. As a builder, I want a measured before and after for each job (what the terminal makes you remember versus the interface), so that the "fewer things to remember" promise can be checked.

---

## Implementation Decisions

### 1. Decisions made (founder, in order)

1. The map ends with a spec, not a build.
2. The interface is for people who do not code.
3. Version 1 covers all six jobs, which cover all 18 commands.
4. Two modes: a full window and a quick popup.
5. It is a desktop app. Toolkit: Electron, confirmed by three checks before build (below). Tauri is the fallback.
6. Ease of use means fewer things to remember or type than the terminal.
7. Airbnb's four principles (unified, universal, iconic, conversational) are written rules, not a copied look.
8. Four user settings: text size, colours (light and dark), quick popup shortcut and position, menu order and visibility.
9. Tested by hand on Debian only. Windows and macOS are built and launch-checked automatically.
10. One test seam: the command layer.
11. First run includes the AI key step.
12. Words come from `GLOSSARY.md`.
13. Palette: Ledger Page (light) and Soot (dark). The first palette file is retired.
14. Signature move: heat. Second move: provenance.
15. Nothing is deleted. Words: Reject, Close, Replaced by.
16. Spacing: seven steps (4, 6, 8, 12, 16, 20, 32 px at Default), in rem so spacing scales with text size.
17. Typeface: Atkinson Hyperlegible Next, with Atkinson Hyperlegible Mono for figures (founder chose the recommendation).
18. Menu bar: define one menu structure in this spec (below).
19. Motion: one moment, a heat mark settling when status changes.
20. This spec is delivered as a file.
21. Undo is built (option A): an undo that appends a new ledger entry. The founder reasoned that no one uses the tool today, so the change is cheap now. Investigation result in section 12.
22. Undo grouping: Option 2. One optional group id column is added to the ledger (decided 2026-10-30). Reasons: no users means no old records to protect, it removes a special case in `set-status`, it removes a clock-tick risk, and it is cheapest now. Option 1 (group by timestamp, no structure change) was the considered alternative and stays a valid fallback.

### 2. Jobs and the commands behind them (Fact, `docs/commands.md`)

| Job | Commands |
|---|---|
| Add | `capture`, `capture-source` |
| Look up | `current-state`, `topic-search`, `why`, `history` |
| Link items | `relate` |
| Fix and close | `set-status`, `close-item`, `edit-item`, `remove-link`, `reverse-supersedes`, `set-validated`, `clear-validated` |
| Clean up | `maintain` |
| Keep safe | `backup`, `export`, `db-check` |

Rules the interface must respect (Fact, same file):
- `edit-item` writes `rationale` on a Decision and `source` on a Finding only. `statement` is forbidden.
- `set-status` moves only between Active and Challenged. A Closed item refuses.
- `set-validated` applies to an Assumption only.
- `close-item` accepts the human reasons `invalidated` and `expired` only.
- `remove-link` marks a link Rejected. It never deletes it.
- `backup` refuses a target that is the source file, rotates an existing target to `.old-1..3`, and verifies the copy. Restore is not a command: open the backup file as the knowledge base.
- `export` is read-only, cannot be restored, and refuses to overwrite the database file.
- `capture`, `relate` and the AI close proposals in `maintain` need an AI key. Every other command works without one.

### 3. Modules

- **Interface layer (new).** Screens, states, settings, shortcuts, menus, tray. No Ember rules live here.
- **Command layer (existing).** The 18 commands. The single test seam. The interface calls these and shows their results.
- **Confirm port (existing).** `capture` and `relate` receive their confirm step from outside (`run_confirm_loop(..., confirm=..., ...)`). The interface supplies a window-based confirm. Tests supply a fake one. *Open:* whether the terminal confirm can be swapped with no code change was read in `capture` only, not in `relate` or `maintain`.
- **Platform shell (new).** Menus, global shortcut, tray icon, window handling.
- **Settings store (new).** Holds the four settings. *Open:* where it lives.
- **Key store (new).** Holds the AI key. *Open:* where it lives. The terminal's script writes a `.env` file in the repository folder, which does not suit an installed app.

### 4. Gaps found between the commands and the screens (Fact where stated)

- **No single "all items" read.** `current-state` omits Closed items. `topic-search` requires a query. Home's Closed count and Look up's full list need an additive read (for example a flag or a new read-only command). Adding optional output is a safe change (`Constitution.md` I10).
- **Machine-readable output.** Query commands print one JSON document (Fact). `capture-source` prints JSON. Other commands print text for people. The interface needs structured results from the commands it uses. Which commands lack it was not checked. Check at the start of build.
- **Provenance.** `why` follows only `depends_on` and `supports`, confirmed links, transitively. The prototype also shows "Challenged by" and "Replaced by". That data needs the item's links, which `history --item` carries as events. Build must combine them or add a read.
- **History needs paging and a date filter.** `history` supports `--limit`, `--offset`, `--since` (ISO-8601 with a UTC offset).

### 5. Screens and states (see the approved prototype and `DESIGN.md`)

Every screen has normal, loading, empty (where it can be empty), error, and no-key states where a key is needed. The prototype drew these. Errors appear inside the block that failed, with what failed and a retry. The title of an error is specific, never just "Error".

### 6. Words

Use glossary words and explain each once on first use: knowledge base, item, proposal, confirm, link, source, ledger, sweep, backup, export. Words to avoid: suggestion, note, card, record, approve, the database. Button labels are one or two words. Cancel is always called Cancel.

### 7. Visual system

`DESIGN.md` is the source (approved). In short: Ledger Page and Soot palettes, heat marks, flat surfaces with 1px rules, one 6px radius, one main button per screen, no gradients, glass, shadows at rest or emoji. Spacing uses seven steps. Light and dark themes pass 4.5:1 for text.

### 8. Type and fonts

Atkinson Hyperlegible Next and Mono, self-hosted (Fact: SIL Open Font License 1.1, so bundling is allowed and each copy must carry the licence text and copyright notice). The build must include the language subsets Ember's users need (Atkinson supports 150+ languages, Fact, Braille Institute). The prototype embeds Latin only. Apple's SF fonts are not shipped (Fact: Apple's fonts page restricts use to registered Apple developers, from an excerpt).

### 9. Menu bar (decision 18)

Defined here as a proposal to confirm at build. It follows Apple's standard order (Fact: App, File, Edit, Format, View, app-specific, Window, Help) and Apple's rule to show the same items always and disable, not hide (Fact).

| Menu | Items |
|---|---|
| Ember (Mac app menu) | About Ember; Settings… (Command+Comma); Hide; Quit |
| File | Add text…; Open a knowledge base file… (Command+O); Back up…; Export…; Close window (Command+W) |
| Edit | Undo (Command+Z), Redo (Shift+Command+Z), each labelled with what it will do; Cut, Copy, Paste, Select All; Find (Command+F focuses search in Look up) |
| View | Show Sidebar / Hide Sidebar |
| Jobs | Home, Add, Look up, Link items, Fix and close, Clean up, Keep safe (Command+1 to Command+7, *Inference:* not on the standard list I read) |
| Window | Minimize; Zoom |
| Help | Ember Help (*Open:* no help content is defined yet) |

- Undo and Redo labels name the action, as Apple describes ("Undo Typing"): for example "Undo Close item 3". When nothing can be undone the item stays visible and disabled.
- Text size is not in the View menu. Apple's standard list contains Command+Hyphen and Shift+Command+Equal.
- On Windows and Linux the same menus sit inside the window and Command becomes Ctrl (*Inference:* Windows and Linux guidelines were not read).
- A tray icon menu offers: Quick add, Open Ember, Quit.

### 10. Shortcuts

- **Quick popup (global).** Default Option+Command+E on a Mac, Ctrl+Alt+E on Windows and Linux. Apple says to avoid Control as a modifier and to prefer Command with Option for power features (Fact). Conflicts with other programs are not detected (*Open*). Fallback: the tray icon.
- **Settings.** Command+Comma on a Mac, Ctrl+Comma elsewhere.
- **Proposal loop.** Return confirms, Esc stops, `e` edits, `n` rejects. `y` and `q` also work. Link proposals use Return (confirm), `s` (skip), `n` (reject).
- Modifier order in any shown shortcut: Control, Option, Shift, Command (Fact, Apple).

### 11. Platform and delivery

- Electron, preferred. Three checks before build: it can run Ember's Python commands, the popup shortcut works on Windows and macOS, and the install size is acceptable to the founder. If a check fails the fallback is Tauri.
- How the interface talks to the Python commands is *Open*. It must not require a server of Ember's own (`README.md` promise).
- Tested by hand on Debian (Fact: founder). Linux with Wayland may block global shortcuts (Fact, QHotkey page). The founder checks this with `echo $XDG_SESSION_TYPE`. The result is not yet known.
- The existing CI job runs only on `ubuntu-latest` (Fact, `.github/workflows/test.yml`). Windows and macOS builds and launch checks need a CI job that runs on those systems. Whether GitHub's free runners cover this was not checked.

### 12. Undo (decided: option A, framed to the edge)

**Question you asked:** does Option A need a change to the structure of the knowledge base file? **Answer: no, it does not need one. One small, optional structure change is recommended for reliability, and your answer to it is needed (12.4).** Undo also cuts across two written design rules, which you must amend (12.3). All facts below were read from the code and plans in `/home/user/ember`. Nothing was changed there.

#### 12.1 What is already true (Fact)

- The ledger table (`change_log`) has no restriction on what kind of entry it holds: `field_changed` and `trigger_cause` are free text, and no database trigger touches that table. The only triggers are on `links` and `items`.
- `items.status` accepts Active, Challenged and Closed. The only item trigger says "Closed requires a close reason". Reopening an item (status Active, close reason empty) is allowed. `links.status` accepts Confirmed and Rejected.
- Every human action already records what it replaced. The old and new status are in the ledger row, written as `Closed:invalidated` for a closed item. Edits store the old value. Link removal stores Confirmed to Rejected.
- Ember already reopens a closed item by appending rows: `reverse-supersedes` does it today, with no structure change.
- The ledger is append-only by convention and by every plan (`plans/master-plan.md` rule 7, `plans/steps/maintain/02-apply-and-cli.md`: "a mistaken status change is corrected by a new row, not by rewriting history"). An undo that appends fits that rule.
- No knowledge base file is tracked in the repository (0 tracked database files, `.gitignore` excludes `*.db`).

#### 12.2 Scope: which actions Undo reverses

| Action | What the ledger holds | How Undo reverses it |
|---|---|---|
| `close-item` (invalidated or expired) | the item's status row, plus one row per dependent challenged (same timestamp, cause `dependency_closed`, with the link) | restore each item's old status and close reason |
| `set-status` | a status row, and, only for Challenged to Active, a second `status_origin` row (value manual) written in a separate transaction at a later timestamp | restore the old status and the earlier shield state |
| `set-validated`, `clear-validated` | a `validated` row (cause `user_set_validated`) | flip the mark back |
| `edit-item` | the field, old value and new value | write the old value |
| `remove-link` | a `link_removed` row, Confirmed to Rejected | set the link Confirmed again (currently forbidden, see 12.3) |
| `reverse-supersedes` | a status row (cause `reversal`, with the link), a `link_reversed` marker, and the link's `reversed_at` | close the item again as superseded, clear `reversed_at`, add a new marker |

**Not covered by Undo:** `capture` confirms (items are never deleted, so an item you regret is closed with Fix and close), `relate` confirms (remove the link with Fix and close), the sweep (it is derived from links, so undoing it would only be re-done by the next sweep), `backup` and `export` (files), and settings.

#### 12.3 Rules in the code that Undo amends (CONFIRMED by the founder, 2026-10-30)

1. **"Only reversal reopens a Closed item."** The `set-status` rule (`MAINTAIN-006`) refuses a Closed item. Undoing a close reopens one. Amend to: "a Closed item reopens by reversal or by undoing its own close".
2. **"The product has no un-remove."** The link-removal write says it must "never INSERT, DELETE, or flip back", and its plan says the clause "forbids flipping Rejected back". Undoing a removal flips it back. Amend to allow the flip only as an undo, recorded as a new ledger row.
3. **The shield.** A human status change is protected from the next sweep until newer link evidence arrives. Undo must restore the shield's earlier state exactly, or the next sweep will behave differently from before. This is the subtlest part and needs its own tests.

Rules 1 and 2 are amended as written above. Rule 3 is a requirement on the build, not an amendment. The reason behind rules 1 and 2 was auditability ("a mistaken removal is auditable forever in the `link_removed` row"). An undo that appends keeps that.

#### 12.4 The one structure question (DECIDED: Option 2, 2026-10-30)

A single user action can write several ledger rows (a close and its challenged dependents). Rows from one batch share one timestamp, because the code reads the clock once per batch. But nothing in the table says "these rows are one action", and `set-status` writes its shield row in a second transaction at a later timestamp.

- **Option 1: no structure change.** Group rows by identical timestamp, and treat `set-status` as a special case. Cost: grouping logic in code, a small risk of two actions sharing a microsecond, and undo that cannot survive a design change to batching.
- **Option 2 (chosen): add one optional column to the ledger, a group id.** Additive and empty for old rows. Ember has done the same twice (close reason in migration 010, project label in migration 012), and it writes a safety copy before an upgrade (`README.md`). Cost: one migration (schema version 13), the checks in `db-check` that name schema versions, and the `export` text, which prints every column of every row. Actions made before the upgrade have no group id, so Undo refuses them with a plain message (user story 123).
- **Records affected by Option 2:** 0 existing rows change (no backfill). 0 database files in the repository. Rows in your own local files: not counted (I cannot see them). The migration is forward-only, as 010 and 012 were. The way back is the safety copy Ember writes before upgrading.
- This is a database structure change, which `AGENTS.md` lists as risky. The founder chose Option 2 on 2026-10-30 after seeing the counts above and the undo path. At build start, before writing the migration, the builder must show the then-current counts again, as `AGENTS.md` requires, and run the migration test on a copy of a knowledge base file.
- **Fallback:** if the migration proves harder than expected, Option 1 remains valid. It would remove the migration, `db-check` and `export` items from 12.5 and keep the rest.
- **Open about the column itself:** its exact name, and whether each undo and redo row also points to the group it reverses (the spec requires the pointer, the form is a build choice).

#### 12.5 Everything else that must change (modules, not files)

- **Maintain engine, human actions:** new validators for undo and redo, new error codes (the last used is `MAINTAIN-022`, so new ones start at 023).
- **Maintain store port:** new writes that apply the inverse and append the ledger row in one transaction.
- **Link reversal replay:** it rebuilds `reversed_at` from `link_reversed` rows only. Undoing a reversal needs a new marker kind, or `db-check` will report drift.
- **Query, history:** it sorts events into nine kinds and files anything else as `unknown`. Add kinds for undone and redone, or the ledger shows "unknown".
- **db-check:** new checks for the group id and for the replay change.
- **export:** the text format changes if a column is added (Option 2), and its tests are byte-for-byte.
- **Command layer:** new `undo` and `redo` commands, each with `--dry-run` and `--db`, following the existing dry-run pattern (`item 3: Closed -> Active (dry-run)`).
- **Tests:** one per row of 12.2, plus the shield, the refusal rule, and a migration test.
- **Interface:** Edit menu items, the Undo and Redo buttons on Fix and close, Command or Ctrl+Z, the plain refusal message, and "Undone" and "Redone" lines in the ledger.

#### 12.6 Rules for Undo and Redo

1. Undo reverses the latest human change not yet undone. Several undos step back in order.
2. Redo is the undo of an undo. A new human change clears what Redo could redo.
3. Undo and redo are themselves recorded in the ledger (cause `user_undo`, `user_redo`). Nothing is erased.
4. **Refusal rule:** Undo is refused with a plain message if any affected item or link has changed since, meaning its current value no longer equals the ledger's recorded new value. A sweep, an add or a link confirm in between can cause that.
5. The undo history comes from the ledger, so it survives closing the app (needs the group id, Option 2).
6. The terminal has the same commands. The window never does more than the terminal.

#### 12.7 Interface decision still open (D1)

Apple: "Avoid displaying alerts for common, undoable actions, even when they're destructive." Today Close is: preview, then a final confirmation naming the item. With Undo, the final confirmation could go.
- **Keep both** (preview, confirm, and Undo): safest, one extra click.
- **Preview plus Undo, no second confirm:** faster. Recommended once Undo is built and tested, not before.
- Not decided. The prototype keeps the confirm.

#### 12.8 What I did not check

- The `relate` gatekeeper's duplicate rules when a removed link comes back (it says a rejected row still counts as used).
- `relate` and `capture` code for any other human-only write.
- Whether `maintain` runs in the middle of a group (concurrent use is out of scope).
- The exact test count, and how long the shield logic takes to prove.
- Whether older Ember versions can open a file at schema version 13.

### 13. Success measure (decision 6)

Count, per job, what the terminal makes you know (command names, flags, numbers, set-up steps) against what the interface needs. Examples from `docs/commands.md`, to be completed at build:

| Job | Terminal needs (approx.) | Interface needs |
|---|---|---|
| Add | `capture` or `capture-source`, `--file`, `--db`, the key script, key loading, confirm keys | Paste text, press a button |
| Look up | choose among 4 commands, `--query`, `--status`, `--type`, `--limit`, `--item`, `--since` with a UTC offset | Type, pick filters, select a row |
| Link items | `relate`, `--item` or `--latest`, an extra package, confirm keys | One button, confirm |
| Fix and close | 7 commands, `--item`, `--link`, `--reason`, `--field`, `--value`, `--to`, `--dry-run` | Pick an item, pick an action, preview, confirm |
| Clean up | `maintain`, `--dry-run`, confirm keys for AI proposals | Preview, apply |
| Keep safe | `backup TARGET`, `export --out`, `db-check`, `--db` | Three buttons, choose a file |

---

## Testing Decisions

**What makes a good test:** it checks what a person can see or do, not how the code is built. A good interface test gives a command the same input as the terminal and checks the interface shows the same result.

**The one seam:** the command layer. Every job the interface offers must give the same result as the matching `ember` command, tested through the same door the terminal tests use. The confirm step is part of that seam: the interface plugs in its own confirm, and tests plug in a fake.

**What to test:**
- For each of the six jobs, run the command layer and the interface adapter on the same knowledge base and compare the result.
- Rules from section 2: each forbidden action stays forbidden through the interface (for example editing a statement, setting a Closed item's status, backing up onto the source file).
- Counts on Home equal the items in the knowledge base.
- Undo: one test per row of section 12.2 (the inverse restores every changed item), the shield, the refusal rule, redo as undo of an undo, and a migration test if Option 2 is chosen. Each runs through the command layer.
- Error codes map to plain sentences, and no screen shows a bare error code.
- Settings survive a restart.

**Prior art (Fact):** `tests/test_cli.py` runs commands through `CliRunner`. There are per-command tests such as `tests/test_backup.py`, `tests/test_export.py`, `tests/test_db_check.py` and `tests/test_cli_capture.py`. `tests/test_architecture.py` enforces the project's layering rule.

**Not covered by tests (say so, then check another way):**
- Look and feel, colours, spacing, and the heat mark motion: checked by screenshot review at 1440, 768 and 390 pixels, and by the design checkers used in the design session. Those checkers are not installed in the repository (founder's rule).
- Windows and macOS: automatic launch checks only, then a person with those machines.
- Keyboard use, screen readers and 200% text: a manual pass, plus an automatic check that no screen overflows at the Largest size. The prototype passed that check at one window size (1360px wide).
- Global shortcut on every system: manual.

---

## Out of Scope

- Building the interface. This spec only decides it.
- Undo of Add, Link confirms and sweeps (section 12.2 says how to reverse each).
- A phone app, a web app, a hosted version, or any cloud storage.
- Several people using one knowledge base at once.
- Languages other than English (not decided; fonts allow it later).
- The Lantern Keeper character in the interface (brand story only).
- A project list screen, a "Needs review" status or counts by project. These appeared in the first palette file's example and do not exist in Ember (`README.md`: statuses are Active, Challenged and Closed).
- Help content for the Help menu.

## Further Notes

**Corrections made during the design session:**
- Ember has 18 commands, not 17. `docs/commands.md` groups two under one heading.
- macOS does not support Dynamic Type (Fact, Apple's typography page). Ember's Text size setting is its own choice that follows the idea.
- Apple publishes no numeric macOS spacing scale that I found. The seven spacing steps are Ember's own, built on older macOS values reported by a third-party guide.
- The prototype once enabled "Edit rationale" and "Edit source" on every item. It now follows the real rules.

**Evidence limits:** no real person has seen the prototype. "People who do not code" is the founder's assumption. The first test with 3 to 5 such people is the way to check it.

**Files delivered with this spec:** `PRODUCT.md` (approved), `DESIGN.md` (approved), `apple-hig-findings.md`, `taste-direction-sheet.md` (inspiration only, random per run), and `PROTOTYPE-ember-interface-v3.html` (made-up data, not connected to Ember).

**Still open (not decided):** the close confirmation (12.7); the interface-to-Python link; settings and key storage; shortcut conflicts; Windows and Linux guidelines; drag and drop; search in the title bar; popup look and behaviour; SF Symbols terms; the toolbars, windows, loading and feedback pages of Apple's guidelines; language subsets for fonts; Help content.
