package ch.bfh.generic_dpp_platform.dpps.models;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;
import java.util.Map;

/**
 * Cache entity for external DPP revisions fetched from other platforms.
 */
@Getter
@Setter
@Entity
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Table(name = "referenced_dpp_revision", indexes = {
        @Index(name = "idx_ref_dpp_fetched_at", columnList = "fetched_at")
})
public class ReferencedDppRevision {

    @EmbeddedId
    private ReferencedDppRevisionId id;

    @Column(name = "subject_type", nullable = false)
    private String subjectType;

    @Column(name = "schema_subject_type", nullable = false)
    private String schemaSubjectType;

    @Column(name = "schema_major_version", nullable = false)
    private Integer schemaMajorVersion;

    @Column(name = "schema_minor_version", nullable = false)
    private Integer schemaMinorVersion;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "dpp_document", nullable = false)
    private Map<String, Object> dppDocument;

    @Column(name = "hashed_document", nullable = false)
    private byte[] hashedDocument;

    @Column(name = "created_at")
    private Instant createdAt;

    @Column(name = "fetched_at", nullable = false)
    private Instant fetchedAt;

    public String getDppId() {
        return id != null ? id.getDppId() : null;
    }

    public Integer getDppVersion() {
        return id != null ? id.getDppVersion() : null;
    }
}
