CREATE TABLE IF NOT EXISTS ingestion_runs (
  id TEXT PRIMARY KEY,
  mode TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  source_count INTEGER DEFAULT 0,
  item_count INTEGER DEFAULT 0,
  error_count INTEGER DEFAULT 0,
  summary_json TEXT
);

CREATE TABLE IF NOT EXISTS information_items (
  id TEXT PRIMARY KEY,
  schema_version TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_id TEXT NOT NULL,
  source_name TEXT,
  collector TEXT,
  external_id TEXT,
  external_url TEXT,
  author_handle TEXT,
  author_display_name TEXT,
  title TEXT,
  content_text TEXT,
  content_hash TEXT NOT NULL,
  language TEXT,
  created_at TEXT NOT NULL,
  collected_at TEXT NOT NULL,
  raw_json TEXT NOT NULL,
  run_id TEXT,
  created_date TEXT GENERATED ALWAYS AS (substr(created_at, 1, 10)) VIRTUAL,
  FOREIGN KEY(run_id) REFERENCES ingestion_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_items_created_at ON information_items(created_at);
CREATE INDEX IF NOT EXISTS idx_items_source_created ON information_items(source_id, created_at);
CREATE INDEX IF NOT EXISTS idx_items_author_created ON information_items(author_handle, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_items_external_unique ON information_items(source_type, external_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_items_hash_unique ON information_items(source_id, content_hash, created_at);

CREATE TABLE IF NOT EXISTS item_entities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  value TEXT NOT NULL,
  normalized_value TEXT NOT NULL,
  confidence REAL DEFAULT 1.0,
  source TEXT,
  metadata_json TEXT,
  FOREIGN KEY(item_id) REFERENCES information_items(id)
);

CREATE INDEX IF NOT EXISTS idx_entities_value ON item_entities(entity_type, normalized_value);
CREATE INDEX IF NOT EXISTS idx_entities_item ON item_entities(item_id);

CREATE TABLE IF NOT EXISTS item_analysis (
  item_id TEXT PRIMARY KEY,
  theme TEXT,
  sentiment TEXT,
  view_label TEXT,
  reason TEXT,
  risk TEXT,
  quote TEXT,
  specific_tickers_json TEXT,
  confidence REAL,
  model_name TEXT,
  analyzed_at TEXT,
  analysis_json TEXT,
  FOREIGN KEY(item_id) REFERENCES information_items(id)
);

CREATE INDEX IF NOT EXISTS idx_analysis_theme ON item_analysis(theme);
CREATE INDEX IF NOT EXISTS idx_analysis_sentiment ON item_analysis(sentiment);

CREATE TABLE IF NOT EXISTS report_snapshots (
  id TEXT PRIMARY KEY,
  report_type TEXT NOT NULL,
  report_date TEXT NOT NULL,
  start_at TEXT NOT NULL,
  end_at TEXT NOT NULL,
  generated_at TEXT NOT NULL,
  report_json TEXT NOT NULL,
  report_html TEXT,
  item_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_reports_date ON report_snapshots(report_type, report_date);

CREATE VIRTUAL TABLE IF NOT EXISTS information_items_fts USING fts5(
  item_id UNINDEXED,
  title,
  content_text,
  author_handle,
  source_name
);
