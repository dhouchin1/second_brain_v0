ALTER TABLE notes ADD COLUMN zettel_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_notes_zettel_id
  ON notes(zettel_id) WHERE zettel_id IS NOT NULL;
