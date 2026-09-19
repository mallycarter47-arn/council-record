-- Council Record schema
-- The searchable unit is an agenda item, not an arbitrary text window.

PRAGMA journal_mode = WAL;

-- ---------------------------------------------------------------------------
-- Source tables
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS bodies (
    body_id     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    type_name   TEXT,
    active      INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS events (
    event_id        INTEGER PRIMARY KEY,
    body_id         INTEGER,
    body_name       TEXT NOT NULL,
    event_date      TEXT NOT NULL,      -- ISO date
    event_year      INTEGER NOT NULL,
    event_time      TEXT,
    location        TEXT,
    agenda_file     TEXT,
    minutes_file    TEXT,
    insite_url      TEXT,               -- deep link to the official record
    video_path      TEXT,               -- v2: transcription hook
    minutes_status  TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_date ON events(event_date);
CREATE INDEX IF NOT EXISTS idx_events_body ON events(body_id);
CREATE INDEX IF NOT EXISTS idx_events_year ON events(event_year);

CREATE TABLE IF NOT EXISTS matters (
    matter_id     INTEGER PRIMARY KEY,
    file_number   TEXT,
    title         TEXT,
    type_name     TEXT,
    status_name   TEXT,
    intro_date    TEXT,
    body_name     TEXT
);

CREATE INDEX IF NOT EXISTS idx_matters_file ON matters(file_number);

-- The core table. One row per agenda item.
CREATE TABLE IF NOT EXISTS agenda_items (
    item_id         INTEGER PRIMARY KEY,
    event_id        INTEGER NOT NULL REFERENCES events(event_id),
    agenda_number   TEXT,
    sequence        INTEGER,
    matter_id       INTEGER,
    matter_file     TEXT,
    matter_type     TEXT,
    matter_status   TEXT,
    title           TEXT,               -- what the item is
    action_name     TEXT,               -- what council did: Approved, Referred...
    action_text     TEXT,
    agenda_note     TEXT,
    minutes_note    TEXT,
    passed_flag     INTEGER,
    -- denormalized from events so search results need no join
    event_date      TEXT NOT NULL,
    event_year      INTEGER NOT NULL,
    body_name       TEXT NOT NULL,
    insite_url      TEXT
);

CREATE INDEX IF NOT EXISTS idx_items_event ON agenda_items(event_id);
CREATE INDEX IF NOT EXISTS idx_items_date ON agenda_items(event_date);
CREATE INDEX IF NOT EXISTS idx_items_year ON agenda_items(event_year);
CREATE INDEX IF NOT EXISTS idx_items_body ON agenda_items(body_name);
CREATE INDEX IF NOT EXISTS idx_items_action ON agenda_items(action_name);

-- ---------------------------------------------------------------------------
-- Full-text index
--
-- content='agenda_items' makes this an external-content table: the text is not
-- duplicated, FTS just indexes it. rowid ties back to agenda_items.item_id.
--
-- porter tokenizer so "demolition" matches "demolitions", "contracting"
-- matches "contract". unicode61 strips punctuation from file numbers sanely.
-- ---------------------------------------------------------------------------

CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
    title,
    action_text,
    agenda_note,
    minutes_note,
    matter_file,
    body_name,
    content='agenda_items',
    content_rowid='item_id',
    tokenize='porter unicode61'
);

-- Keep FTS in sync with the base table.
CREATE TRIGGER IF NOT EXISTS agenda_items_ai AFTER INSERT ON agenda_items BEGIN
    INSERT INTO items_fts(rowid, title, action_text, agenda_note, minutes_note,
                          matter_file, body_name)
    VALUES (new.item_id, new.title, new.action_text, new.agenda_note,
            new.minutes_note, new.matter_file, new.body_name);
END;

CREATE TRIGGER IF NOT EXISTS agenda_items_ad AFTER DELETE ON agenda_items BEGIN
    INSERT INTO items_fts(items_fts, rowid, title, action_text, agenda_note,
                          minutes_note, matter_file, body_name)
    VALUES ('delete', old.item_id, old.title, old.action_text, old.agenda_note,
            old.minutes_note, old.matter_file, old.body_name);
END;

CREATE TRIGGER IF NOT EXISTS agenda_items_au AFTER UPDATE ON agenda_items BEGIN
    INSERT INTO items_fts(items_fts, rowid, title, action_text, agenda_note,
                          minutes_note, matter_file, body_name)
    VALUES ('delete', old.item_id, old.title, old.action_text, old.agenda_note,
            old.minutes_note, old.matter_file, old.body_name);
    INSERT INTO items_fts(rowid, title, action_text, agenda_note, minutes_note,
                          matter_file, body_name)
    VALUES (new.item_id, new.title, new.action_text, new.agenda_note,
            new.minutes_note, new.matter_file, new.body_name);
END;

-- ---------------------------------------------------------------------------
-- Bookkeeping
-- ---------------------------------------------------------------------------

-- Lets ingest resume after a crash or a ctrl-C instead of starting over.
CREATE TABLE IF NOT EXISTS ingest_progress (
    event_id     INTEGER PRIMARY KEY,
    items_loaded INTEGER NOT NULL,
    fetched_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingest_log (
    id           INTEGER PRIMARY KEY,
    source       TEXT NOT NULL,
    events_loaded INTEGER NOT NULL,
    items_loaded INTEGER NOT NULL,
    earliest     TEXT,
    latest       TEXT,
    ingested_at  TEXT NOT NULL
);
