CREATE TABLE ai_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    response_text TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
