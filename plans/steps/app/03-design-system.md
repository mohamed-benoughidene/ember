# L3 App Step 3: the design system as code

Status: DRAFT 2026-10-30. Parent: `plans/interface-app-plan.md` §5.8. Source of truth: `docs/DESIGN.md` (approved) and the prototype. Needs step 02.

## Constitution rules this step enforces
B5 (a few deep components), T1 (pure helpers), D3 (tokens defined once), I10 (tokens additive), S2.

## Deferred settings resolved by this step
- Font language subsets (L2 §9): the founder names the languages his users need; default Latin only until he answers. Shipping more is additive.

## 1. Boundary shapes
- `app/renderer/styles/tokens.css`: every token of `DESIGN.md` (Ledger Page and Soot palettes, seven spacing steps `--s1..--s7` in rem, one radius, type scale, five text sizes). No value appears twice anywhere else.
- Fonts under `app/assets/fonts/` with the SIL OFL 1.1 text and copyright notice in the same folder and in the About box (spec story 108). No network font loading.
- Components with fixed contracts (props/events only): HeatMark (Active = full dot, Challenged = half dot, Closed = ring; accessible name; settle motion on status change; no motion under Reduce Motion), StatusPill, ProvenanceLine, ItemRow, ProposalBlock, StateBlock (loading / empty / error with Retry and Details / no-key), Button (one primary per screen), Banner.
- Pure helpers: `textScale(step)`, `rem` conversion, contrast check used in tests.

## 2. Tests
- Unit: token file contains every `DESIGN.md` token name (parse both); HeatMark shape per status; StateBlock renders all four states.
- Contrast test: every text/background pair in both palettes ≥ 4.5:1 (computed, real numbers shown).
- Visual check (not covered by tests): screenshots at 1440, 768, 390 px in light/dark at Default and Largest; compared to the prototype by the founder.
- No horizontal overflow at Largest on a sample screen (automatic).

## 3. Check command (S1)
```
$ npm --prefix app test -- design      -> token, contrast and component tests pass
$ npm --prefix app run gallery         -> opens a page showing every component in every state, both themes
```

## 4. Error codes raised
None.

## 5. Rollback
Revert the commit. No data or Python change.

## 6. Done when
Tests pass with real counts; the founder has looked at the gallery in both themes and approved it.
