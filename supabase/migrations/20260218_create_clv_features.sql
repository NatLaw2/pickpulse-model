-- CLV Timing Features table
-- Stores computed timing features for each locked pick.
-- Optional: can be skipped if schema changes are risky.
-- Populated by: python -m app.clv_timing.backfill

CREATE TABLE IF NOT EXISTS clv_features (
    id              BIGSERIAL PRIMARY KEY,
    event_id        TEXT NOT NULL,
    locked_at       TIMESTAMPTZ,
    computed_at     TIMESTAMPTZ DEFAULT NOW(),
    side            TEXT,       -- 'home' or 'away'

    -- Core CLV
    p_lock          DOUBLE PRECISION,
    p_close         DOUBLE PRECISION,
    clv_prob        DOUBLE PRECISION,

    -- Steam / velocity
    steam_5m        DOUBLE PRECISION,
    steam_15m       DOUBLE PRECISION,
    velocity_30m    DOUBLE PRECISION,
    range_30m       DOUBLE PRECISION,
    std_30m         DOUBLE PRECISION,

    -- Snapshot gap quality
    snap_gap_lock_sec   DOUBLE PRECISION,
    snap_gap_close_sec  DOUBLE PRECISION,

    -- Snapshot timestamps used
    lock_snap_ts    TIMESTAMPTZ,
    close_snap_ts   TIMESTAMPTZ,

    UNIQUE (event_id, locked_at)
);

-- Index for quick event lookups
CREATE INDEX IF NOT EXISTS idx_clv_features_event ON clv_features(event_id);

-- Index for CLV analysis queries
CREATE INDEX IF NOT EXISTS idx_clv_features_clv ON clv_features(clv_prob);
