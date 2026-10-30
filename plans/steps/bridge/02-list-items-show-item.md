# L3 Bridge Step 2: `list-items` and `show-item`

Status: DRAFT 2026-10-30. Parent: `plans/interface-bridge-plan.md` §5.3. Phase: read gaps. Independent of step 01.

## Constitution rules this step enforces
I10 (additive commands), T1 (pure cores), T9, B2 (reads only through `QueryLookupPort`), D3, I4, I8 (empty KB is a valid answer), I12.

## Deferred settings resolved by this step
None. (Paging defaults: no limit unless `--limit` given, as `history`.)

## 1. Boundary shapes (cite L2 §5.3)
- `QueryLookupPort` is NOT widened if the existing four reads suffice: `list_items()` already returns all items in Query's read model, and `list_links()` all links. Verify in the first test; if a column is missing (rationale, source, validated, close_reason, created_at) add it to the read model additively.
- Pure core `list_items(items, filter, page)` and `show_item(item_id, items, links, source_text)` in `ember/query/`; `run_list_items`, `run_show_item` entry points validate, load, derive, render (`json.dumps` only, like the other query renderers).
- `show_item` returns: the item row, its source text (verbatim), `links_out` and `links_in` (every status, `reversed_at`, other item's id/type/statement/status). Source text comes through one new read `source_text_for(item_id)` on the lookup port (Query's read-only boot, no write path).
- Boot: `open_query_database` (read-only, floor 10, never migrates).

## 2. Tests
- Unit: all-statuses listing includes Closed; filter + page reuse `validate_topic_filter` semantics (`QUERY-006` `field=`); `total` is the pre-page count; `show_item` includes Rejected and reversed links; unknown id → `QUERY-001`.
- Integration, real temp DB seeded by `tests/fakes.py` helpers; read-only hash proof (DB byte-identical).
- CLI: exit codes, JSON-only stdout, usage errors exit 2.

## 3. CLI check (S1)
```
$ ember list-items --status Closed --db t.db   -> {"total":1,"items":[{"id":3,...}]}   [exit 0]
$ ember show-item --item 3 --db t.db           -> {"item":{...},"source":"...","links_out":[...],"links_in":[...]}   [exit 0]
$ ember show-item --item 99 --db t.db          -> error: QUERY-001 ...   [exit 1]
```

## 4. Error codes raised
QUERY-001, QUERY-003, QUERY-004, QUERY-006 (reused, unchanged meaning).

## 5. Rollback
Revert the commit. Two new read-only commands; nothing stored.

## 6. Done when
Suite passes with real counts; `docs/commands.md` and `README.md` list both commands and `tests/test_docs_in_sync.py` passes.
