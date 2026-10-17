CREATE TABLE item_embeddings (
    item_id INTEGER PRIMARY KEY REFERENCES items(id),
    vector BLOB NOT NULL,
    model_name TEXT NOT NULL,
    embedded_at TEXT NOT NULL
);
