ALTER TABLE change_log RENAME TO change_log_old;
CREATE TABLE change_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER REFERENCES items(id),
    link_id INTEGER REFERENCES links(id),
    field_changed TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    timestamp TEXT NOT NULL,
    trigger_cause TEXT NOT NULL
);
INSERT INTO change_log (id, item_id, link_id, field_changed, old_value, new_value, timestamp, trigger_cause)
    SELECT id, item_id, link_id, field_changed, old_value, new_value, timestamp, trigger_cause
    FROM change_log_old;
DROP TABLE change_log_old;
