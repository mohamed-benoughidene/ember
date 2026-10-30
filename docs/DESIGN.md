---
name: Ember
description: A calm desktop record of what a project decided, assumed, found and asked, where every item shows how hot it is.
colors:
  paper-ground: "#D6CCBA"
  ledger-paper: "#E9E2D4"
  aged-paper: "#DDD3C1"
  worn-paper: "#CFC4B0"
  rule-line: "#CBBFAA"
  control-line: "#8E8068"
  iron-ink: "#2B2118"
  faded-ink: "#5A4B3D"
  brick-wash: "#9C3B2B"
  brick-deep: "#7A2D20"
  ember-heat: "#B8421F"
  ochre-wash: "#E0C88F"
  ochre-ink: "#3A2A0A"
  soot-ground: "#14100E"
  soot-surface: "#1D1714"
  soot-raised: "#261E1A"
  soot-line: "#2E2520"
  soot-sidebar: "#0D0A09"
  soot-ink: "#EDEAE6"
  soot-faded-ink: "#B0ABA4"
  soot-heat: "#F08A3E"
  warm-apricot: "#F5C090"
typography:
  title:
    fontFamily: "Atkinson Hyperlegible Next, system-ui, -apple-system, Segoe UI, Roboto, Noto Sans, sans-serif"
    fontSize: "1.6rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  heading:
    fontFamily: "Atkinson Hyperlegible Next, system-ui, -apple-system, Segoe UI, Roboto, Noto Sans, sans-serif"
    fontSize: "1.1rem"
    fontWeight: 600
    lineHeight: 1.5
  body:
    fontFamily: "Atkinson Hyperlegible Next, system-ui, -apple-system, Segoe UI, Roboto, Noto Sans, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Atkinson Hyperlegible Next, system-ui, -apple-system, Segoe UI, Roboto, Noto Sans, sans-serif"
    fontSize: "0.87rem"
    fontWeight: 500
    lineHeight: 1.5
  figure:
    fontFamily: "Atkinson Hyperlegible Mono, ui-monospace, SF Mono, Menlo, Consolas, DejaVu Sans Mono, monospace"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  control: "6px"
spacing:
  step-1: "4px"
  step-2: "6px"
  step-3: "8px"
  step-4: "12px"
  step-5: "16px"
  step-6: "20px"
  step-7: "32px"
components:
  button-primary:
    backgroundColor: "{colors.brick-wash}"
    textColor: "#FFFFFF"
    rounded: "{rounded.control}"
    padding: "0.5rem 0.9rem"
  button-primary-hover:
    backgroundColor: "{colors.brick-deep}"
  button-secondary:
    backgroundColor: "{colors.ledger-paper}"
    textColor: "{colors.iron-ink}"
    rounded: "{rounded.control}"
    padding: "0.5rem 0.9rem"
  nav-item-selected:
    backgroundColor: "{colors.ledger-paper}"
    textColor: "{colors.iron-ink}"
    rounded: "{rounded.control}"
---

# Design System: Ember

> APPROVED by the founder on 2026-10-30 as written. Palette: Ledger Page (light) and Soot (dark). Typeface: Atkinson Hyperlegible Next and Mono, chosen by the founder. Motion is built in the prototype.

## Overview

**Creative North Star: "The Field Journal, Lit by an Ember"**

A plain, readable record kept by a careful custodian. The ground is aged paper and iron-gall ink. Ember colour appears in one place with real meaning: the heat mark that shows an item's status. The product reads as a serious knowledge tool, not a fantasy game. The Lantern Keeper stays in the brand story and does not appear in the interface.

**The signature move: heat.** Every item shows how hot it is. A full dot is Active, a half dot is Challenged (needs a second look), an empty ring is Closed (ash). The shapes differ, so status never depends on colour alone. Orange or brick means status or the one main action, never decoration. Only Ember has a glowing core and a status lifecycle driven by evidence, so no other product can use this move truthfully.

**Second move: provenance.** Selecting an item shows where it came from and what challenged or replaced it, in plain lines: Source, Why, Challenged by, Replaced by.

**Key Characteristics:**
- Aged-paper surfaces, iron-brown ink, one dark sidebar.
- The operating system's own sans for text, and a mono face for item numbers, dates and counts (data, not decoration).
- Flat. Depth comes from tone steps and thin rules, not shadows.
- Plain words from the glossary. No emoji, no decoration.
- A dark theme (Soot) with equal contrast.

## Colors

**Source of the light palette (Fact, measured):** the Met Museum's public-domain "Interior Decorator's Account Book of Hours Spent" (1846, accession 2013.496). Measured on its page image: paper about #D4C9B7 (a greyed buff), faded brick wash #A16058, ochre #B1905B, ink #524535. The UI uses those hues, lightened or darkened only where contrast needs it. The page is a real object, not a mood board.

### Light (Ledger Page)
- **Paper Ground** (#D6CCBA): the window background.
- **Ledger Paper** (#E9E2D4): panels, tables, inputs, content area.
- **Aged Paper** (#DDD3C1): notices and the title bar.
- **Worn Paper** (#CFC4B0): selected table row, status tint.
- **Rule Line** (#CBBFAA): panel and table separators. **Control Line** (#8E8068): input and button outlines.
- **Iron Ink** (#2B2118): main text and the sidebar. 12:1 on Ledger Paper.
- **Faded Ink** (#5A4B3D): secondary text. 6.4:1 on Ledger Paper, 5.1:1 on Paper Ground.
- **Brick Wash** (#9C3B2B): the one main button per screen. White text 6.8:1. Hover Brick Deep (#7A2D20).
- **Ember Heat** (#B8421F): status marks only. 4.2:1 on Ledger Paper (a non-text mark needs 3:1).
- **Ochre Wash** (#E0C88F) with **Ochre Ink** (#3A2A0A): the "Challenged" tint where one is needed.

### Dark (Soot)
Warm near-black, not navy or slate. Ground #14100E, surface #1D1714, raised #261E1A, lines #2E2520, sidebar #0D0A09, text #EDEAE6, secondary text #B0ABA4 (7.5:1), heat #F08A3E (7.1:1). The main button is light (#EDEAE6 with dark text), so orange never means two things. The selected menu row is Warm Apricot (#F5C090) with Charred Wood text (10.2:1).

### Named Rules
**The Heat Only Rule.** Orange and brick mark status or the one main action. If a screen has neither, it has no ember colour.
**The Real Paper Rule.** The light ground is greyed buff, never bright cream. Bright cream is the common AI default and both design tools flag it.

## Typography

**Font: Atkinson Hyperlegible Next** for all text, with **Atkinson Hyperlegible Mono** for item numbers, ledger dates and counts. Fallback: the operating system's sans.

**Why this font (a functional reason, not a mood):** Braille Institute made it for low-vision readers so that letters are easy to tell apart (Fact, Braille Institute and Fontsource). In a ledger of item numbers, 1, l and I, and 0 and O, must never be confused. It supports the 200% text setting and the "universal" principle. It is not on Impeccable's list of default faces to avoid.
**Licence (Fact, SIL Open Font License 1.1, Fontsource):** the font may be bundled in the app, and each copy must carry the licence text and copyright notice. The font cannot be sold by itself. Self-host the files so Ember makes no font request on the network.
**Compared and rejected:** the system font (no character) and Lexend (wider letters wrap the sidebar hints, and its reading-improvement claims come from its own website, not checked).
**Open:** the prototype embeds only the Latin subset. Atkinson Hyperlegible Next supports 150+ languages (Fact, Braille Institute), so the build must include the subsets Ember's users need. Weights used: 400, 500, 600.

**Character:** quiet and clear. The mono figures give the ledger a record-keeper's rhythm.

### Hierarchy
- **Title** (600, 1.6rem, 1.2): one noun per screen.
- **Heading** (600, 1.1rem): section names.
- **Body** (400, 1rem, 1.5): reading text, 65 to 75 characters per line.
- **Label** (500, 0.87rem): field labels, table headers, small notes. Sentence case.
- **Figure** (mono, tabular numerals): No. columns, dates, counts.

### Named Rules
**The Text Size Rule.** All sizes and spacing are in rem. The user setting has five steps: Small 14px, Default 15px, Large 17px, Larger 22px, Largest 30px. Largest is 200% of Default, which meets Apple's guidance to offer at least 200%. At Larger and Largest the sidebar narrows to 11rem and hides its hints, and rows and notices wrap.

## Spacing

**Adapted from Apple, not copied.** What I could verify (Fact): Apple's SwiftUI tutorial says the system picks default spacing between views, and lets you use a fixed value or spacing that scales with text size (ScaledMetric). A third-party guide to older macOS guidelines gives 20pt from the window edge, 8pt sideways and 6pt vertically between controls, 8pt between columns, and at least 20pt each side of a divider. I found no official numeric macOS spacing scale on Apple's Layout page, which lists numbers for tvOS and visionOS only. So the seven steps below are Ember's own scale built on those anchors. Do not describe them as an official Apple scale.

**Seven steps (rem, equal to these pixels at Default text size):**

| Step | px | Use |
|---|---|---|
| 1 | 4 | Tight gaps: title to subtitle, list row padding |
| 2 | 6 | Related things stacked: label to field, field to help text |
| 3 | 8 | Sideways between controls, icon to label, table cell vertical padding, button vertical padding |
| 4 | 12 | Table cell sideways padding, short block gaps |
| 5 | 16 | Panel padding, button sideways padding, gap between fields |
| 6 | 20 | Window and content margin, gap between groups, between title row and content |
| 7 | 32 | Between major sections, settings row gap |

**Rules:**
1. **Relationship decides spacing.** Related things sit close (steps 2 and 3). Separate groups sit apart (steps 6 and 7).
2. **Only these seven.** No other spacing value appears in the interface. The prototype used 23 different values before this scale and uses 7 now.
3. **Spacing scales with text size.** Steps are in rem, so Ember's Text size setting (Small, Default, Large) grows and shrinks the gaps with the writing. This follows the idea behind Apple's Dynamic Type and ScaledMetric. Correction: Apple states that macOS does not support Dynamic Type (it exists on iOS, iPadOS, tvOS, visionOS and watchOS), so this is an Ember choice, not a macOS convention.
4. **Open:** Apple's body text is 13pt and Ember's is 15px, so the numbers are tuned for slightly larger text. Not tested with real people.

## Motion

**One authored moment: a heat mark settles when its item changes.** A new item lights up (a full dot scales in with a small overshoot, about 260ms). An item becoming Challenged turns into a half dot (about 240ms). An item becoming Closed cools into a ring (about 240ms). Only transform and opacity move.

**Rules:** nothing animates on page load or when you revisit a screen. Marks move only at the moment of change, where the change is visible (the Saved so far list while adding, the changed items after a sweep, the Fix screen). With Reduce Motion on, nothing moves. This follows Apple's guidance: "Aim for brevity and precision in feedback animations."

## Layout

A window up to 1180px. A 15rem sidebar and one content column with step 6 (20px) padding. Each screen has a title row (title, one sentence, the one main button), then its answer first, then detail. The sidebar collapses to icons below 800px. First run keeps the same frame: a step list on the left, the step form on the right. The quick popup is a 440px window with only Add and a path to the full window.

## Elevation & Depth

Flat by default. Surfaces are separated by tone steps and 1px rules. No shadows at rest. Inline confirmation replaces dialogs.

### Named Rules
**The No Modal First Rule.** Confirmations appear in place and name the object ("Close item 3, ...").

## Shapes

One corner radius for controls and panels: 6px. Status is a heat mark with a word, not a coloured pill. Selected rows are filled, never marked by a coloured left edge.

## Components

- **Heat mark:** 12px. Full dot Active, half dot Challenged, ring Closed. Always followed by the word.
- **Primary button:** Brick Wash (light) or light-on-dark (dark), one per screen.
- **Secondary button:** Ledger Paper with a Control Line outline. **Text button:** underlined, no outline.
- **Danger button:** outlined in Brick Wash, after a preview, with an inline confirmation that names the object.
- **Disabled controls:** stay readable and say why.
- **Menu row:** 16px outline icon, name, one-line hint. Selected row is filled. A count badge appears only on Clean up, only when changes are pending.
- **Table:** 14px sentence-case grey headers, 1px rules, no zebra, mono numbers.
- **Provenance list:** label column and value column: Source, Why, Challenged by, Replaced by, Answered by.
- **Proposal card:** type, statement, quote from the source, a check message if the gatekeeper warns. Buttons run left to right: Stop (Esc), Edit (e), Reject (n), Confirm (Return). The main choice is on the trailing side, as Apple's alert guidance says. The keys y and q also work. Link proposals use Skip (s), Reject (n), Confirm (Return).
- **Ledger entry:** mono timestamp, plain sentence, "Confirmed by you" when a person confirmed it.
- **Empty, loading, error:** empty keeps its frame with one sentence; loading shows grey bars at real size; errors appear in the failed block with a retry.
- **Settings:** four panes in a tab row: Appearance (text size, colours), Quick popup (shortcut, position), Menu (which jobs show and in what order), AI connection. Opens with Command+Comma on a Mac and Ctrl+Comma elsewhere. The window title names the pane, and the last pane is remembered. Each control saves itself and shows a quiet "Saved".
- **Popup shortcut:** default Option+Command+E on a Mac and Ctrl+Alt+E on Windows and Linux. Keys are listed in Apple's order: Control, Option, Shift, Command. On a Mac the setting warns about Control (the system uses it), about no modifier, and about standard Command shortcuts. Conflicts with other programs are not detected.

## Do's and Don'ts

### Do
- Answer each screen's one question first, in its biggest element.
- Use glossary words and explain each once.
- Show heat on every item, with its word.
- Say that nothing is deleted: use Reject, Close, Replaced by. Never "Delete".
- Preview and name the object before anything that cannot be undone.

### Don't
- No gradients, glows, glass, shadows at rest, emoji, or icons in coloured squares.
- No small uppercase labels above headings, no numbered section labels.
- No coloured left bar on selected rows or notices.
- No rows of identical cards, no card inside a card.
- Don't use ruled-paper textures or handwriting fonts. A literal ledger costume is a known mistake on working screens.
- Don't show the Lantern Keeper in the interface.
- Don't use Control as the modifier in a Mac shortcut. Apple says the system uses it.

## Known conflicts with the design tools

- Taste Skill and Impeccable flag cream grounds as an AI default. The Ledger Page ground is greyed buff measured from a real object, and the Taste inspector reports 0 fail and 0 warn on it. The Impeccable detector was run on the earlier cream version only.
- Taste Skill prefers a sidebar on the page ground. Impeccable says a committed shell colour is a legitimate job for colour. The dark sidebar stays.
- The mono face for figures triggers one Taste lint warning. Taste's own app rules allow mono for IDs and figures.
