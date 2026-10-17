PRAGMA foreign_keys=OFF;
BEGIN;
ALTER TABLE ai_responses RENAME TO ai_responses_old;
CREATE TABLE ai_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER REFERENCES sources(id),
    item_id INTEGER REFERENCES items(id),
    response_text TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
INSERT INTO ai_responses (id, source_id, item_id, response_text, timestamp)
    SELECT id, source_id, NULL, response_text, timestamp
    FROM ai_responses_old;
DROP TABLE ai_responses_old;
COMMIT;
PRAGMA foreign_keys=ON;
