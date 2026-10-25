ALTER TABLE items ADD COLUMN close_reason TEXT CHECK (close_reason IS NULL OR close_reason IN ('answered', 'invalidated', 'superseded', 'reversed', 'expired'));
ALTER TABLE items ADD COLUMN status_origin TEXT NOT NULL DEFAULT 'derived' CHECK (status_origin IN ('derived', 'manual'));
