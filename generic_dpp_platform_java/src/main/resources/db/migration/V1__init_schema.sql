CREATE TABLE IF NOT EXISTS subject_type
(
    name        VARCHAR(255) NOT NULL PRIMARY KEY,
    description TEXT
);

CREATE TABLE IF NOT EXISTS dpp_schema
(
    major_version     INTEGER                     NOT NULL,
    minor_version     INTEGER                     NOT NULL,
    subject_type_name VARCHAR(255)                NOT NULL,
    schema_document   JSONB                       NOT NULL,
    CONSTRAINT PK_DPP_SCHEMA PRIMARY KEY (major_version, minor_version, subject_type_name),
    CONSTRAINT FK_DPP_SCHEMA_ON_SUBJECT_TYPE FOREIGN KEY (subject_type_name) REFERENCES subject_type (name)
);

CREATE TABLE IF NOT EXISTS logical_dpp
(
    dpp_id            VARCHAR(255) PRIMARY KEY,
    subject_type_name VARCHAR(255)                NOT NULL,
    created_at        TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT FK_LOGICAL_DPP_ON_SUBJECT_TYPE FOREIGN KEY (subject_type_name) REFERENCES subject_type (name)
);

CREATE TABLE IF NOT EXISTS dpp_revision
(
    dpp_version          INTEGER                     NOT NULL,
    dpp_id               VARCHAR(255)                NOT NULL,
    schema_major_version INTEGER                     NOT NULL,
    schema_minor_version INTEGER                     NOT NULL,
    subject_type_name    VARCHAR(255)                NOT NULL,
    dpp_document         JSONB                       NOT NULL,
    hashed_document      BYTEA                       NOT NULL,
    created_at           TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT PK_DPP_REVISION PRIMARY KEY (dpp_version, dpp_id),
    CONSTRAINT FK_DPP_REVISION_ON_LOGICAL_DPP FOREIGN KEY (dpp_id) REFERENCES logical_dpp (dpp_id),
    CONSTRAINT FK_DPP_REVISION_ON_DPP_SCHEMA FOREIGN KEY (schema_major_version, schema_minor_version, subject_type_name) REFERENCES dpp_schema (major_version, minor_version, subject_type_name),
    CONSTRAINT FK_DPP_REVISION_ON_SUBJECT_TYPE FOREIGN KEY (subject_type_name) REFERENCES subject_type (name),
    -- Check constraints, the version must be positive and unique for a given logical DPP (Invariant 1)
    CONSTRAINT CHK_VERSION_POSITIVE CHECK (dpp_version > 0),
    CONSTRAINT DPP_ID_VERSION_UNIQUE UNIQUE (dpp_id, dpp_version)
);