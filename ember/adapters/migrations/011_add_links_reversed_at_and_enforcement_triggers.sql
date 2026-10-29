-- Guard (#23 pre-assertion): migration dies if any v10 row breaks the new rule.
CREATE TABLE _guard_011 (bad INTEGER NOT NULL CHECK (bad = 0));
INSERT INTO _guard_011 (bad)
    SELECT COUNT(*) FROM items WHERE status = 'Closed' AND close_reason IS NULL;
DROP TABLE _guard_011;

-- #20: reversal state on the row. NULL = live. Derived data (D3), source stays
-- change_log (master plan rule 7). D5: new optional field, no rename.
ALTER TABLE links ADD COLUMN reversed_at TEXT;

-- Backfill = the replay rule (§6) applied once at migration time.
UPDATE links SET reversed_at = (
    SELECT cl.timestamp FROM change_log AS cl
    WHERE cl.link_id = links.id AND cl.field_changed = 'link_reversed'
    ORDER BY cl.id DESC LIMIT 1
) WHERE EXISTS (
    SELECT 1 FROM change_log AS cl
    WHERE cl.link_id = links.id AND cl.field_changed = 'link_reversed'
);

-- #17: pair table, 16 rows generated from compat.py TYPE_COMPAT (drift test §7).
CREATE TABLE link_compat (
    source_type TEXT NOT NULL,
    target_type TEXT NOT NULL,
    link_type TEXT NOT NULL,
    UNIQUE (source_type, target_type, link_type)
);
INSERT INTO link_compat (source_type, target_type, link_type) VALUES
    ('Decision', 'Assumption', 'depends_on'),
    ('Decision', 'Finding', 'depends_on'),
    ('Decision', 'Decision', 'depends_on'),
    ('Decision', 'Decision', 'supersedes'),
    ('Decision', 'Question', 'answers'),
    ('Assumption', 'Finding', 'depends_on'),
    ('Assumption', 'Assumption', 'depends_on'),
    ('Assumption', 'Assumption', 'supersedes'),
    ('Finding', 'Assumption', 'supports'),
    ('Finding', 'Assumption', 'contradicts'),
    ('Finding', 'Decision', 'supports'),
    ('Finding', 'Decision', 'contradicts'),
    ('Finding', 'Finding', 'contradicts'),
    ('Finding', 'Finding', 'supersedes'),
    ('Finding', 'Question', 'answers'),
    ('Question', 'Question', 'supersedes');

-- §8 symmetric pre-assertion for links (decision closed as option B): migration
-- dies if any existing links row violates TYPE_COMPAT. A pre-existing illegal
-- pair must not migrate silently. Same throwaway-guard pattern as above.
CREATE TABLE _guard_011_links (bad INTEGER NOT NULL CHECK (bad = 0));
INSERT INTO _guard_011_links (bad)
    SELECT COUNT(*) FROM links AS l
    WHERE NOT EXISTS (
        SELECT 1 FROM link_compat
        WHERE source_type = (SELECT type FROM items WHERE id = l.source_item_id)
          AND target_type = (SELECT type FROM items WHERE id = l.target_item_id)
          AND link_type = l.link_type
    );
DROP TABLE _guard_011_links;

-- #17: DB-level pair enforcement. INSERT plus the three mutation columns on UPDATE
-- (the #20/#21 writes touch only reversed_at, which never fires this trigger).
CREATE TRIGGER links_compat_insert BEFORE INSERT ON links
FOR EACH ROW
WHEN NOT EXISTS (
    SELECT 1 FROM link_compat
    WHERE source_type = (SELECT type FROM items WHERE id = NEW.source_item_id)
      AND target_type = (SELECT type FROM items WHERE id = NEW.target_item_id)
      AND link_type = NEW.link_type
)
BEGIN
    SELECT RAISE(ABORT, 'links: pair not in link_compat');
END;

CREATE TRIGGER links_compat_update BEFORE UPDATE OF source_item_id, target_item_id, link_type ON links
FOR EACH ROW
WHEN NOT EXISTS (
    SELECT 1 FROM link_compat
    WHERE source_type = (SELECT type FROM items WHERE id = NEW.source_item_id)
      AND target_type = (SELECT type FROM items WHERE id = NEW.target_item_id)
      AND link_type = NEW.link_type
)
BEGIN
    SELECT RAISE(ABORT, 'links: pair not in link_compat');
END;

-- #23: Closed implies close_reason. items is NOT rebuilt.
CREATE TRIGGER items_closed_reason_insert BEFORE INSERT ON items
FOR EACH ROW
WHEN NEW.status = 'Closed' AND NEW.close_reason IS NULL
BEGIN
    SELECT RAISE(ABORT, 'items: Closed requires close_reason');
END;

CREATE TRIGGER items_closed_reason_update BEFORE UPDATE OF status, close_reason ON items
FOR EACH ROW
WHEN NEW.status = 'Closed' AND NEW.close_reason IS NULL
BEGIN
    SELECT RAISE(ABORT, 'items: Closed requires close_reason');
END;
