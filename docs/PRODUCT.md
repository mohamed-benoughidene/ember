# Product

<!-- impeccable:product-schema 1 -->

> APPROVED by the founder on 2026-10-30 as written. Written by the agent from facts the founder confirmed in the design session and from the repository's own files. Items marked **Open** are undecided on purpose. Undo is still pending (see the spec).

## Platform

web

Delivered as a desktop app. Planned toolkit: Electron, to be confirmed by three checks (see Capabilities and Constraints). A desktop wrapper around web screens does not change the platform value above.

## Users

People on a project team who do not code and who need to keep what the project decided, assumed, found and asked. They find the terminal hard. Their jobs: add text and confirm what Ember proposes, look up why something was decided, fix or close an item, keep the file safe.

**Open:** no real person has been asked or observed yet. "Non-coders" is the founder's assumption. The founder is the only confirmed user today.

## Product Purpose

Ember is a local-first knowledge base for project decisions. It keeps decisions, assumptions, findings and questions as items. It links them and records every change in a ledger. Success for the interface: a person who does not code can do every job the 18 terminal commands do, with fewer things to remember or type than the terminal needs (command names, flags, item numbers).

## Positioning

Ember only proposes. A person confirms every item and every link before anything is saved. Nothing is deleted: removed links are marked Rejected and every change stays in the ledger. The knowledge base is one local file, and Ember needs no server of its own.

## Operating Context

- Today Ember is a command-line tool (18 commands, listed as 17 entries in `docs/commands.md`, Python 3.12 or newer, one SQLite file).
- Founder tests on Linux (Debian) only. Windows and macOS are built and launch-checked by automation, not tested by hand.
- Two window modes: a full window and a quick popup opened from a keyboard shortcut.
- Adding text and linking items need an AI key (OpenRouter). Text sent to those commands goes to an AI service. The other jobs work without a key.

## Capabilities and Constraints

- Six jobs, covering all 18 commands: Add, Look up, Link items, Fix and close, Clean up (the sweep), Keep safe (backup, export, health check).
- Four user settings: text size, light or dark colours, quick popup shortcut and position, menu order and visibility.
- Words come from `GLOSSARY.md`: knowledge base, item, proposal, confirm, link, source, status, ledger, sweep, backup, export. Words to avoid: suggestion, note, card, record, approve, the database.
- Ember has no restore command by design. Restore means opening a backup file as the knowledge base.
- One test seam: every interface job gives the same result as the matching `ember` command, tested through the command layer.
- **Open:** toolkit. Electron is preferred. Checks before build: it can run Ember's Python, the popup shortcut works on Windows and macOS, and install size is acceptable. Tauri is the named fallback.
- **Open:** the popup shortcut may be blocked on some Linux display systems (Wayland). Fallback: a system tray icon.
- **Open:** where the AI key is stored on the user's computer.
- **Open:** a dark-theme version of the logo (the prototype brightens it with a filter).
- Typeface decided by the founder: Atkinson Hyperlegible Next and Mono (SIL Open Font License; ship the licence text with the app). **Open:** language subsets. Motion is built as one moment: a heat mark settles when status changes.
- **Open:** the wording for non-coders (glossary words are used, with one-line explanations on first use).

## Brand Commitments

- Name and logo: Ember, a dark cracked stone with a glowing core. Source file: `assets/icon.svg`.
- Palette (decided by the founder, replaces the first palette file): Ledger Page for light, with colours measured from a public-domain 1846 account book at the Met Museum, and Soot for dark. The original Ember palette (Charred Wood, Dark Ember, Flame, Amber Glow, Warm Apricot) is retired as the UI palette. Warm Apricot is kept for the selected menu row in dark.
- Character: "an old field journal illuminated by an ember": warm, restrained, readable, functional. Ember colour marks status (the heat mark) and the one main action, never decoration.
- Signature move: heat. Every item shows how hot it is: full dot Active, half dot Challenged, ring Closed. Plus provenance lines: where an item came from and what challenged or replaced it.
- Voice: nothing is deleted. Use Reject, Close, Replaced by. Never "Delete".
- The Lantern Keeper (the brand's character) belongs to the brand story. The product interface prioritizes clarity and does not show the Keeper.
- Role of the product: custodian and witness. Not owner, not final authority.
- Design reference: Airbnb's four principles as written rules: unified, universal, iconic, conversational. Airbnb's look is not copied.

## Evidence on Hand

- `README.md`, `GLOSSARY.md`, `docs/commands.md`, `Constitution.md` and `PROJECT_MAP.md` in the repository.
- Two worked-example PDFs for non-coders in `docs/Graphs/`.
- A clickable prototype (made-up data) and screenshots from this session.
- **Absent, do not invent:** user research, testers, customer quotes, usage numbers, install-size measurements, and any test on Windows or macOS.

## Product Principles

1. Ember proposes, the person decides. Every save needs a confirm.
2. Every change leaves a trace. History is never erased.
3. Plain words first. Use the glossary words and explain each once.
4. Fewer things to remember than the terminal. Measure each job by terms, numbers and flags avoided.
5. A calm record, not a game. Clarity beats character in the interface.

## Accessibility & Inclusion

- Text meets WCAG AA contrast (4.5:1) in light and dark themes.
- Text size is a user setting with five steps up to 200% of Default (Apple guidance: offer at least 200%).
- Every control works from the keyboard, with a visible focus ring and an accessible name.
- **Open:** other languages. Not decided. "Universal" is an Airbnb principle the interface follows by not hard-coding layout to English word lengths.

## Open Items for the Spec (from Apple's guidelines research, not decided)

Source: `apple-hig-findings.md`. Each item needs a founder decision or more research before build.

1. **Undo (DECIDED: option A, appends a ledger entry).** Investigation found no structure change is required. One optional ledger column (a group id) is recommended, and two written engine rules must be amended. Full framing in `ember-interface-spec.md` section 12. Grouping decided: Option 2 (one optional group id column, 2026-10-30). The two engine rule amendments are confirmed (2026-10-30). Still open: whether Close keeps its final confirmation.
2. **Menu bar.** DECIDED (founder chose to define it in the spec): one menu structure is written in `ember-interface-spec.md`. Build still needs a tester or an automated check on a Mac.
3. **Search position.** Apple: "If search is important, give it a primary position." Search is inside Look up today. Option: a search field in the title bar on every screen.
4. **Drag and drop.** Dropping a file or text onto the window to start Add would match the terminal's `capture --file`. Not read in Apple's guidelines, so unverified.
5. **Quick popup behaviour.** Apple's guidelines say nothing I found about a Spotlight-style popup. Its look, focus behaviour and closing rules are not yet designed.
6. **Shortcut conflicts.** The default popup shortcuts are untested on every system.
7. **Windows and Linux guidelines.** Not read. Apple's guidance is a source of principles, not a rule for those systems.
8. **SF Symbols and SF font.** Apple's fonts page allows its fonts only "if you are a registered Apple Developer" (excerpt only). Ember uses the system font stack and its own icons. The full licence and SF Symbols terms were not read.
9. **Toolbars, window rules, loading and feedback pages.** Not read.
