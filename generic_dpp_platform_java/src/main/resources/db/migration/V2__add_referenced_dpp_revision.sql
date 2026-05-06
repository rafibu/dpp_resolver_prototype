CREATE TABLE referenced_dpp_revision (
    dpp_id VARCHAR(255) NOT NULL,
    dpp_version INTEGER NOT NULL,
    subject_type VARCHAR(255) NOT NULL,
    schema_subject_type VARCHAR(255) NOT NULL,
    schema_major_version INTEGER NOT NULL,
    schema_minor_version INTEGER NOT NULL,
    dpp_document JSONB NOT NULL,
    hashed_document BYTEA NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE,
    fetched_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (dpp_id, dpp_version)
);

CREATE INDEX idx_ref_dpp_fetched_at ON referenced_dpp_revision (fetched_at);
