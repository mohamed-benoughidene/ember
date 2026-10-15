CREATE TABLE sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    full_text TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE
);
