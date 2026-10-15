# L3 Capture Step 2: AI Port + Call (Phase 2)

Implements Phase 2 of L2 Capture plan. Send raw text + context to AI, get back typed item proposals.

## 1. Job

Take `{source_id, raw_text}` from Step 1 and produce a list of proposals from the AI. Each proposal = `{type, statement, source_quote, confidence}`.

## 2. Inputs

- From Step 1: `{source_id, raw_text}`.
- From env: `EMBER_CAPTURE_CONTEXT_MODE` = `A` (no context) or `B` (last 50 items). Default = `B`.
- From env: AI provider config (API key, model name). Adapter owns this.

## 3. Outputs

`[{type: enum, statement: str, source_quote: str, confidence: float}]`

- `type` = one of `Decision`, `Assumption`, `Finding`, `Question`.
- `statement` = AI's typed item text.
- `source_quote` = exact substring from `raw_text` that grounds the statement.
- `confidence` = AI self-rated 0.0-1.0.

## 4. Steps

1. Read env `EMBER_CAPTURE_CONTEXT_MODE` (default `B`).
2. If mode = `B`:
   - Query last 50 items from `items` table ordered by `created_at DESC`.
   - DB read = normal app read (L2 Section 5 L99).
   - Build context payload: `[{id, type, statement}]`.
3. Build AI request payload:
   - `raw_text` (the pasted text).
   - `context` (last 50 items if mode B, else empty list).
   - System prompt instructs AI: pick from 4 types, return proposals with `source_quote` (exact substring) and `confidence`.
4. Call AI via port.
   - Port name: `ItemProposerPort` (L3 decision per L2 Section 8 item 1).
   - Port pattern fixed in L2; this step defines the concrete signature: `propose(raw_text, context) -> list[proposal]`.
   - Adapter implements the port (e.g. OpenAI, Anthropic). Engine core only knows the port.
5. Parse AI response. Validate each proposal:
   - `type` ∈ {Decision, Assumption, Finding, Question}.
   - `statement` non-empty.
   - `source_quote` non-empty AND substring of `raw_text`.
   - `confidence` ∈ [0.0, 1.0].
6. Drop proposals that fail validation. Log drop reason to STDOUT (info, not error).
7. Return surviving proposals to caller (Phase 3).

## 5. Errors

- AI call fail (timeout, network, schema): **retry policy = 1 retry, 0s backoff (immediate)**. If 2nd call also fails, exit 1 with reason.
- AI response unparseable: treat as call fail, retry.
- All proposals fail validation: log "0 valid proposals" to STDOUT, return empty list. Phase 4 will exit 0 with no items to confirm.

## 6. Test Targets

Unit (mocked AI port + mocked DB):
- Mode A: no context read happens.
- Mode B: context read happens, last 50 items passed to AI.
- Retry policy: 1st call fail -> 2nd call made. 2nd call fail -> exit 1.
- Validation: proposal with bad type dropped. Proposal with non-substring quote dropped. Proposal with out-of-range confidence dropped.
- All-invalid: empty list returned, no exit.

Integration (real AI via fixture):
- Use saved AI response fixtures. Assert parsed output schema + types. Never assert exact prose (L2 Section 5 L102).

## 7. Out of Scope (this step)

- Gatekeeper validation against existing DB (Step 3, Phase 3).
- User confirm + write (Step 3, Phase 4).
- AI adapter choice (OpenAI vs Anthropic). Adapter implements `ItemProposerPort`.

## 8. Next

Step 3 takes these proposals, runs gatekeeper (Phase 3), and prompts user to confirm (Phase 4).

## 9. Deferred Settings (from L2 Section 8)

- AI port name (item 1) — L3 picks. This step uses `ItemProposerPort`.
- AI retry policy (item 2) — L3 picks count + backoff. This step enforces it: 1 retry, 0s backoff.

## 10. Settings Already Fixed by L2 (NOT deferred)

- Context window size — L2 §3 L31 already fixed at 50. This step uses 50 as default. Not from L2 §8.
