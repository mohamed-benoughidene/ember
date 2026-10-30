# Build plans (history)

These plans record how Ember was built and why each choice was made. They are kept as history. The code and [`docs/commands.md`](../docs/commands.md) are the source of truth.

## Read this first

- Some details are out of date. For example, `master-plan.md` says Ember has four engines. It now has five, because the Utility engine (backup, export, health check) was added later.
- If a plan and the code disagree, trust the code.
- Code comments refer to plan sections, such as "L2 section 5.4". Those sections live in these files.

## How the plans are layered

- **L1, the whole system:** [`master-plan.md`](master-plan.md).
- **L2, one plan per engine:**
  - [`engine-capture-plan.md`](engine-capture-plan.md)
  - [`engine-relate-plan.md`](engine-relate-plan.md)
  - [`engine-maintain-plan.md`](engine-maintain-plan.md)
  - [`engine-query-plan.md`](engine-query-plan.md)
  - [`engine-utility-plan.md`](engine-utility-plan.md)
- **Hardening, after the first four engines shipped:**
  - [`hardening-plan.md`](hardening-plan.md): the phase plan for the open issues left over.
  - [`hardening-schema-plan.md`](hardening-schema-plan.md): rules the knowledge base file enforces itself.
  - [`hardening-decisions.md`](hardening-decisions.md): decisions the maintainer recorded on 2026-10-29.
- **L3, one small plan per build step:** the [`steps/`](steps/) folder, with one subfolder per engine and one for hardening.

For a one-line description of every file, see [`PROJECT_MAP.md`](../PROJECT_MAP.md).
