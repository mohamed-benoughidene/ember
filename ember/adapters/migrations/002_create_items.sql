CREATE TABLE items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK (type IN ('Decision', 'Assumption', 'Finding', 'Question')),
    statement TEXT NOT NULL,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    status TEXT NOT NULL DEFAULT 'Active' CHECK (status IN ('Active', 'Challenged', 'Closed')),
    created_at TEXT NOT NULL,
    validated INTEGER CHECK (validated IN (0, 1))
);
