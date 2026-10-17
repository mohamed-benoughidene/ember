CREATE TABLE links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_item_id INTEGER NOT NULL REFERENCES items(id),
    target_item_id INTEGER NOT NULL REFERENCES items(id),
    link_type TEXT NOT NULL CHECK (link_type IN ('supports', 'contradicts', 'depends_on', 'supersedes', 'answers')),
    status TEXT NOT NULL CHECK (status IN ('Confirmed', 'Rejected')),
    created_at TEXT NOT NULL,
    UNIQUE (source_item_id, target_item_id, link_type),
    CHECK (source_item_id != target_item_id)
);
