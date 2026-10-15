# Project Map

This file lists every file and its purpose in the repository. Update it when files or folders are added or removed.

## Root Files
- `AGENTS.md`: Rules for AI coding agents working in this repository.
- `Constitution.md`: Core build rules for modules, data, interfaces and tests (AI caveman version).
- `Personal guidelines.md`: Rules for tone, accuracy and review style (AI caveman version).
- `PROJECT_MAP.md`: This file. Index of files and their purpose.
- `README.md`: Overview of the Ember project, its core purpose, and repository layout.
- `SECURITY.md`: Security vulnerability reporting instructions and policy.

## GitHub Config (`.github/`)
- `.github/CODEOWNERS`: Defines code and documentation ownership for pull requests.
- `.github/dependabot.yml`: Dependabot settings. Watches GitHub Actions versions each week.
- `.github/pull_request_template.md`: Default checklist and summary template for pull requests.
- `.github/ISSUE_TEMPLATE/bug_report.md`: Issue template for reporting bugs.
- `.github/ISSUE_TEMPLATE/feature_request.md`: Issue template for suggesting improvements.

## Documentation (`docs/`)
- `docs/brand-philosophy.md`: Brand meaning behind the name Ember, the logo, and the Lantern Keeper character.
- `docs/pain statment.md`: The problem the product solves, written as a pain statement.

### AI Versions (`docs/ai version/`)
- `docs/ai version/brand-philosophy-ai.md`: Brand philosophy, terse caveman style for AI readers.
- `docs/ai version/planning-framework-ai.md`: 3-level planning framework (L1 System, L2 Engine, L3 Step), terse caveman style for AI readers.
- `docs/ai version/project-context-system-v1-ai.md`: Project Context System V1 spec, terse caveman style for AI readers.

### Human Versions (`docs/humen version/`)
- `docs/humen version/brand-philosophy-humen.md`: Brand philosophy, plain English for human readers.
- `docs/humen version/Constitution-humen.md`: Core build rules, plain English for human readers.
- `docs/humen version/Personal guidelines-humen.md`: Tone, accuracy and review rules, plain English for human readers.
- `docs/humen version/project-context-system-v1-human.md`: Project Context System V1 spec, plain English for human readers.

### Diagrams and Examples (`docs/Graphs/`)
- `docs/Graphs/V1 Master Diagram Project Context Management System – Master diagram.html`: Visual diagram of the system architecture.
- `docs/Graphs/V1 Master Diagram Project Context Management System-1.pdf`: PDF export of the master diagram.
- `docs/Graphs/V1 Example Run the blue button story – Example run.html`: Worked example showing the system in use.
- `docs/Graphs/V1 Example Run the blue button story-4.pdf`: PDF export of the worked example.

## Active Brand Assets (`assets/`)
- `assets/logo.svg`: Main Ember logo, vertical format.
- `assets/logo-horizontal.svg`: Ember logo, horizontal format for wide spaces.
- `assets/icon.svg`: Small square Ember icon.

## Archived Assets (`archive/assets/`)
Earlier logo and character images, kept for history.
- `archive/assets/ChatGPT Image Oct 14, 2026, 09_11_14 PM.jpg`
- `archive/assets/Charred Ember Emblem Logo.png`
- `archive/assets/Ember_ Lantern Keeper Concept Sheet.png`
- `archive/assets/Ember Logo with Glowing Rock Icon.png`
- `archive/assets/Ember Preserve_ Illustrated Rockscape.png`
- `archive/assets/Ember Rock Logo on Cream Background.png`
- `archive/assets/Molten Ember Shard Emblem.png`

## Planning Documents (`plans/`)
- `plans/master-plan.md`: L1 System Master Plan. 4 engines (Capture, Relate, Maintain, Query), shared SQLite storage, global rules, test strategy, L1 §0 stack decisions.
- `plans/engine-capture-plan.md`: L2 Capture engine master plan. Pipeline phases 1-4 (source storage, AI proposal, gatekeeper, user confirm + write).
- `plans/steps/capture/01-source-storage.md`: L3 Step 1 plan. Phase 1, source dedup by content hash.
- `plans/steps/capture/02-ai-port-call.md`: L3 Step 2 plan. Phase 2, AI proposal via `ItemProposerPort`.
- `plans/steps/capture/03-user-confirm-write.md`: L3 Step 3 plan. Phases 3+4, gatekeeper + user confirm + write.

## Empty Folders
These folders exist but hold no files yet.
- `draft/`: Working drafts.
- `reports/`: Generated reports.
- `research/`: Research notes.
