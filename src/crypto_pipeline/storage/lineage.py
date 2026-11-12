"""Additive run and gap metadata. No synthetic market observations."""
SCHEMA = """
CREATE TABLE pipeline_runs (
 run_id TEXT PRIMARY KEY NOT NULL, started_ms INTEGER NOT NULL, ended_ms INTEGER,
 mode TEXT NOT NULL, trigger TEXT, status TEXT NOT NULL CHECK(status IN ('running','succeeded','failed')),
 error TEXT
);
CREATE TABLE run_sources (
 run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id),
 raw_file_id INTEGER REFERENCES raw_files(id), metadata_source_id INTEGER REFERENCES metadata_sources(id),
 CHECK((raw_file_id IS NULL) != (metadata_source_id IS NULL)),
 UNIQUE(run_id,raw_file_id), UNIQUE(run_id,metadata_source_id)
);
CREATE TABLE monitoring_windows (
 exchange TEXT NOT NULL, symbol TEXT NOT NULL, dataset TEXT NOT NULL CHECK(dataset IN ('oi','klines')),
 interval TEXT NOT NULL CHECK(interval='5m'), start_ms INTEGER NOT NULL CHECK(start_ms%300000=0),
 checked_through_ms INTEGER, reconciled_ms INTEGER,
 PRIMARY KEY(exchange,symbol,dataset,interval)
);
CREATE TABLE observation_gaps (
 exchange TEXT NOT NULL, symbol TEXT NOT NULL, dataset TEXT NOT NULL, interval TEXT NOT NULL,
 bucket_end_ms INTEGER NOT NULL CHECK(bucket_end_ms%300000=0),
 detected_ms INTEGER NOT NULL, reconciled_ms INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('missing','recovered')), recovered_ms INTEGER,
 detected_run_id TEXT REFERENCES pipeline_runs(run_id), recovered_run_id TEXT REFERENCES pipeline_runs(run_id),
 raw_file_id INTEGER REFERENCES raw_files(id),
 PRIMARY KEY(exchange,symbol,dataset,interval,bucket_end_ms),
 FOREIGN KEY(exchange,symbol,dataset,interval) REFERENCES monitoring_windows(exchange,symbol,dataset,interval),
 CHECK((status='missing' AND recovered_ms IS NULL AND raw_file_id IS NULL) OR
       (status='recovered' AND recovered_ms IS NOT NULL AND raw_file_id IS NOT NULL))
);
CREATE INDEX idx_gaps_status ON observation_gaps(status,exchange,symbol,dataset,bucket_end_ms);
"""
