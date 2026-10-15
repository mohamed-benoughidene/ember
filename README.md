# Ember

> **Project Context Management System**
> Preserving the evolving state of what a project knows, believes, decides, and learns over time.

---

## What is Ember?

When teams work on software or products, they make decisions, discover facts, test assumptions, and ask questions. Over time, that knowledge gets lost inside old chat logs, commit histories, or people's heads.

Ember is a system for maintaining that durable context. It does not store the project itself (like code files or images). Instead, it stores the understanding **around** the project: why choices were made, what is currently unproven, and what new findings change our thinking.

---

## Core Principles

- **Durable Knowledge Only:** Focuses on persistent knowledge that alters how a project is understood, not raw code or daily to-do lists.
- **Traceable History:** Items are never deleted. State changes (like an assumption becoming invalid) are preserved with their causes.
- **Strict Boundaries:** External data and AI outputs pass through validation scripts before entering the system.
- **Fast, Local-First:** Designed to run with a local database on your own computer with zero mandatory servers.

---

## Repository Structure

- `Constitution.md`: Architectural rules for standalone modules, clean boundaries, and reliable tests.
- `PROJECT_MAP.md`: Index of every file and directory in this project.
- `Personal guidelines.md`: Working guidelines on accuracy, plain language, and critical thinking.
- `docs/`: System documentation, brand philosophy, and architecture diagrams.
  - `docs/ai version/`: Compressed specifications optimized for AI readers.
  - `docs/humen version/`: Plain-English specifications written for human builders.
  - `docs/Graphs/`: Visual diagrams and example runs.
- `assets/`: Official Ember brand logos and icons.

---

## Status

Ember is currently in the active specification and V1 architecture stage.
