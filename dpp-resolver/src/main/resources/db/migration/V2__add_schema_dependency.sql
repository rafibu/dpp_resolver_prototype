CREATE TABLE IF NOT EXISTS schema_dependency
(
    from_subject_type_id BIGINT  NOT NULL,
    to_subject_type_id   BIGINT  NOT NULL,
    schema_major         INTEGER NOT NULL,
    schema_minor         INTEGER NOT NULL,
    CONSTRAINT pk_schema_dependency PRIMARY KEY (from_subject_type_id, to_subject_type_id, schema_major, schema_minor),
    CONSTRAINT fk_dep_from_schema FOREIGN KEY (schema_major, schema_minor, from_subject_type_id)
        REFERENCES dpp_schema (major_version, minor_version, subject_type_id),
    CONSTRAINT fk_dep_to_subject_type FOREIGN KEY (to_subject_type_id)
        REFERENCES subject_type (id),
    CONSTRAINT chk_no_self_reference CHECK (from_subject_type_id <> to_subject_type_id)
);

CREATE INDEX idx_dep_from ON schema_dependency (from_subject_type_id);
CREATE INDEX idx_dep_to ON schema_dependency (to_subject_type_id);
