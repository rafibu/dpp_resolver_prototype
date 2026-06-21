CREATE TABLE IF NOT EXISTS query_attribute_fact
(
    -- We only have one query attribute fact per logical dpp and path.
    logical_dpp_id VARCHAR      NOT NULL,

    subject_type   VARCHAR(255) NOT NULL REFERENCES subject_type (name),
    path           VARCHAR(255) NOT NULL,

    value_text     TEXT,
    value_number   NUMERIC,
    value_boolean  BOOLEAN,

    PRIMARY KEY (logical_dpp_id, path),

    CONSTRAINT fk_qaf_logical_dpp
        FOREIGN KEY (logical_dpp_id)
            REFERENCES logical_dpp (dpp_id)
            ON DELETE CASCADE,

    CONSTRAINT ck_qaf_one_value
        CHECK (
            (value_text IS NOT NULL AND value_number IS NULL AND value_boolean IS NULL)
                OR
            (value_text IS NULL AND value_number IS NOT NULL AND value_boolean IS NULL)
                OR
            (value_text IS NULL AND value_number IS NULL AND value_boolean IS NOT NULL)
            )
);

CREATE INDEX idx_qaf_subject_path
    ON query_attribute_fact (subject_type, path);

CREATE INDEX idx_qaf_text_lookup
    ON query_attribute_fact (subject_type, path, value_text);

CREATE INDEX idx_qaf_number_lookup
    ON query_attribute_fact (subject_type, path, value_number);

CREATE INDEX idx_qaf_boolean_lookup
    ON query_attribute_fact (subject_type, path, value_boolean);