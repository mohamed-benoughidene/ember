# T50 — the live test: every button, one pass

You are testing the **installed app** (Ember 0.2.0 from the `.deb`).
Goal: press every button once and compare what happens with "you should
see". Anything different — even small — write it down **with the step
number**. Each difference becomes one fix ticket, same as every finding
so far.

Before you start (5 minutes):

- [ ] Use a **test knowledge base file**, never your real one. The
      first-run step below creates one for you (a name ending in
      `-test` keeps it obvious, e.g. `/home/mo/ember-test.db`).
- [ ] Have your **real AI key** ready to paste (this is the one thing
      we must test for real).
- [ ] Keep this file open beside Ember. Tick the boxes as you go.

---

## 1. First run (3 steps)

1. Start Ember (menu or `ember-app`).
   - You should see: the first-run screen, step 1 of 3.
2. Type the test file path in the knowledge-base box (`/home/mo/ember-test.db`)
   → **Continue**.
   - You should see: step 2, the AI key.
3. Paste your key → **Save the key**.
   - You should see: the key saved, shown only as its last 4 characters,
     never the whole key.
4. In the same step try one wrong case first: click **Save the key**
   with an empty box.
   - You should see: "The key box is empty. Paste your key, then save it."
5. Click **Skip for now** once, then reopen Settings → AI connection and
   paste the key properly (you must have a key for steps 3 and 5 below).
6. Finish first run with **Add your first text**.
   - You should see: the Add screen with an empty text box.

## 2. Home

7. Click **Home** in the left sidebar (first item).
   - You should see: what needs attention first, the counts per status,
     the item count total, the latest ledger lines.
8. Click **Add text** (the button on Home).
   - You should see: the Add screen, same as step 1.6.
9. Click **Home** again; find **View the whole ledger** if shown.
   - You should see: the ledger list (newest first).

## 3. Add (your real key does real work here)

10. Paste 2–3 short real notes (2–4 sentences each), one per Add.
11. For the first proposal, press **Reject** (`n`).
    - You should see: the proposal refused, nothing saved, the loop
      moves on.
12. For the next proposal, click **Edit** (`e`).
    - You should see: small fields to change (type, statement…), then
      **Confirm**.
13. Confirm the rest with **Confirm** (`Return`).
    - You should see: each saved item appear in **Saved so far** with
      its heat mark, then a summary with counts.
14. On the summary, click **Link the new items**.
    - You should see: the Link items screen (step 5).
15. Start one more Add and press **Stop** (`Esc`) mid-loop.
    - You should see: the run stops, nothing half-written; the summary
      or empty state is honest about it.
16. Start one Add with a piece of text with no clear facts.
    - You should see: an honest empty state ("nothing to propose" style)
      and your text kept as a source only.

## 4. Look up

17. Click **Look up** in the sidebar.
    - You should see: search box, status and type filters, a count line,
      the items table with heat marks.
18. Type a word from one note into the search box.
    - You should see: the list narrows; the count updates.
19. Click the status filter (Closed etc.) and the type filter once each.
    - You should see: each narrows the list correctly (check the count).
20. Click one row.
    - You should see: the item's provenance — verbatim source text, why,
      and all links both directions with the other item's heat mark.
21. Click the **Ledger** tab.
    - You should see: every change as rows you can read in plain words.
22. In the ledger: set the **item filter** to a number, then clear it;
    set the **since** date; click **Older lines** / **Newer lines** if
    shown.
    - You should see: the rows filter and page; older pages still read
      in plain words.

## 5. Link items (the one REAL model run — the check we owe)

23. Click **Link items** in the sidebar; pick an item from the list
    (click the row).
    - **First run can take minutes** (the model loads from the bundled
      files — this machine-time is exactly what we need to see once).
24. On a proposal: press **Confirm** (`y`/`Return`) once, **Skip** (`s`)
    once, **Reject** (`n`) once.
    - You should see: confirmed links appear in **Linked so far** with
      the settle animation; skipped/rejected add nothing.
25. Press **Stop** (`Esc`/`q`).
    - You should see: a clean stop with the engine's own counts.
26. Read the note under the links list.
    - You should see: "not undone by the Undo button — Fix and close
      removes a link".

## 6. Fix and close (+ Undo and Redo)

27. Click **Fix and close** in the sidebar; pick an item.
    - You should see: its current status and actions.
28. Click **Mark Challenged** (on an Active item).
    - You should see: the change applied with a plain confirming
      sentence; the Undo label appears.
29. Press **Undo** (bar button and `Ctrl+Z`).
    - You should see: "Undo Set status…" style label; after it runs, the
      item is back; the label flips to **Redo**.
30. Press **Redo** (`Ctrl+Shift+Z`).
    - You should see: the change applied again.
31. Click **Mark Active** / **Mark Challenged** once more on another item.
32. On an Assumption item: toggle the **verified** mark.
    - You should see: the mark set (Findings/Decisions do not offer it).
33. Click **Edit rationale** (or **Edit source**), change the text,
    click **Preview**, then confirm.
    - You should see: a dry-run preview (old → new) before anything is
      written, then the change with a confirming sentence.
34. Pick an item with a dependent and click **Preview closing**/
    **Close item…** with reason invalidated.
    - You should see: the close preview listing the dependent item(s),
      then a final inline confirmation with **Cancel**. Cancel once,
      then confirm for real.
35. Open the item list and **Undo replacement** (reverse a supersedes)
    on a superseded pair, if you made one.
    - You should see: the replacement reversed; the older item is back.
36. Try to undo until nothing is left.
    - You should see: an honest disabled/hint state ("nothing to undo"),
      never a crash.

## 7. Clean up (the sweep)

37. Click **Clean up** in the sidebar; click **Preview the sweep**.
    - You should see: the pre-flight table (which item becomes what and
      why) and the **Apply** button carrying the change count on its
      label. With 0 changes, Apply stays off/locked.
38. Click **Apply** (if there is at least one change) and answer one
    question with **Confirm**, one with **Reject**, then **Stop**.
    - You should see: one proposal block per stale question in the
      pinned order Stop / Reject / Confirm; `y`/`n`/`Esc` on the
      keyboard do the same; the summary with settled heat marks at the
      end; the badge on the sidebar refreshes.
39. Run **Preview the sweep** again with nothing stale.
    - You should see: an honest empty/zero result, no key needed.

## 8. Keep safe

40. Click **Keep safe** in the sidebar.
    - You should see: the health check auto-run with every line in
      plain words and a verdict (OK expected).
41. Click **Run the check again**.
    - You should see: the same clean verdict.
42. Click **Back up now**.
    - You should see: where the backup went, the item count, and
      (on a second run) the kept older copy.
43. Click **Export as text…**, choose a file.
    - You should see: the exported text file exists, and the screen
      says it **cannot be restored into Ember**.
44. Click **Open a different file…**, first choose a NON-Ember file
    (any text file).
    - You should see: a refusal in plain words before anything opens.
45. Then open the `ember-test.db` file itself (or another valid one) and
    confirm.
    - You should see: the one confirmation naming the file and saying
      the current file is unchanged, then the switch.

## 9. Settings (all five tabs)

46. Click **Settings** (sidebar, LAST item) or press `Ctrl+,` — both must
    work.
47. **Appearance:** set text size step by step to **Largest (200%)** —
    check 2–3 other screens grow correctly; set colours Light, then
    Dark, then System.
    - You should see: everything scales from the tokens; nothing
      overlaps or clips at 200%.
48. **Quick popup:** click **Change keys** and press a new shortcut
    (e.g. `Ctrl+Alt+T`), watch the warning line if it clashes; click
    **Use the default** to go back. Try **Position**: switch to
    top-centre, open the popup, then back to bottom-right.
    - You should see: the shortcut re-registers; the popup appears where
      the setting says, clamped on-screen.
49. **Menu:** hide one job (e.g. Link items) and move one up/down.
    - You should see: the sidebar order follows (Home stays first,
      Settings last); the hidden job shows disabled in the Jobs menu,
      never vanished.
50. **AI connection:** the status shows only the masked hint; click
    **Replace key**, re-paste, save; open **Remove key…**, read the
    careful preview, click **Cancel** (do not remove).
    - You should see: masked hint updates (last 4 characters); removal
      asks first.
51. **Knowledge base file:** click **Verify**/**Use this file** on the
    current one.
    - You should see: an OK verification; a non-Ember file is refused
      with plain words.

## 10. The menu bar, top to bottom

52. **Ember** menu: **About Ember** (font credits + version 0.2.0),
    **Settings…**, **Hide** (minimises on Linux), **Quit** — try each
    (Quit last, reopen after).
53. **File**: **Add text…** (opens the quick popup), **Open a knowledge
    base file…**, **Back up…**, **Export…**, **Close window**.
    - You should see: each lands where its name says.
54. **Edit**: the **Undo**/**Redo** items show live labels ("Undo Close
    item 3"-style) and work; **Find** jumps to Look up and focuses the
    search box.
55. **View**: sidebar toggle on/off.
56. **Jobs**: one item per job with `Ctrl+1..7` — press two of them.
    - You should see: the screens switch; hidden jobs are disabled
      (grey), never missing.
57. **Window**/**Help**: standard entries (Minimize, Zoom, Help).
    - You should see: nothing dead; help opens something honest.

## 11. Quick popup and tray

58. Press the popup shortcut (`Ctrl+Alt+E` by default).
    - You should see: the small add window near the saved position;
      the draft text kept from last time if any.
59. In the popup: add one text end-to-end; press `Esc` mid-loop (stop);
    close after Stop; click **Open Ember** — the main window comes
    forward, the popup stays honest.
60. Click the **tray icon** (panel).
    - You should see: the menu Quick add / Open Ember / Quit — try all
      three (Quit closes Ember; reopen).

## 12. Accessibility (5 minutes, worth it)

61. In Settings → Appearance set **Largest**, walk three screens with
    **Tab only**.
    - You should see: a visible focus ring on every stop; nothing
      unreachable; nothing horizontally cut off (the design rule's
      Largest-text adaptation).
62. Turn **Reduce Motion** on; make a status change.
    - You should see: the settle animation suppressed.
63. If you have a screen reader (Orca): read Home and one proposal
    block.
    - You should see: names that make sense, statuses not by colour
      alone.

## 13. When something is off

Note the step number + one sentence of what you saw vs expected
(a photo/screenshot is gold). Send me the list — each item becomes one
fix ticket with the same process as every finding so far. Do NOT try to
repair anything yourself inside the app.

## Also owed (answer during/after the walk)

- Always-on-top for the main window is built OFF — do you want it ON?
- Popup default position is bottom-right — keep it, or centred where the
  mouse is (the step-11 default)?
- Esc/draft defaults in the popup felt right?
