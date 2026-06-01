package ch.bfh.generic_dpp_platform.dpps.models;

import ch.bfh.generic_dpp_platform.dpps.utils.DppUtil;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchema;
import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import lombok.extern.slf4j.Slf4j;
import org.hibernate.annotations.ColumnDefault;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;
import java.util.Arrays;
import java.util.Map;

/**
 * Represents a revision of a Digital Product Passport (DPP). Each revision is identified
 * by an embedded ID that includes the DPP ID and version. This class is tied to a specific
 * LogicalDpp entity and its schema, while encapsulating metadata and the actual DPP content.
 * It ensures the integrity of stored DPP document content by verifying hashed values before
 * persisting or updating.
 * <br>
 * The DppRevision entity includes:
 * - A composite identifier for the DPP revision (ID and version).
 * - An association with the corresponding LogicalDpp entity.
 * - A reference to the associated schema, identified by version and subject type name.
 * - A JSON-like DPP document payload and its hashed representation for integrity.
 * - A timestamp for when the revision was created.
 * <br>
 * Features:
 * - The `verifyHashIntegrity` method calculates the hash of the document content on persist/update
 * and ensures that it matches the stored hash. If they differ, an exception is thrown to maintain
 * data integrity.
 * - Provides access to the DPP version via the `getVersion` method.
 * <br>
 * Constraints:
 * - The content document (`dppDocument`) is stored as JSON while its integrity is enforced through hashing.
 * - Associations with other entities, including schemas and logical DPPs, enforce referential integrity.
 */
@Slf4j
@Getter
@Setter
@Entity
@Table(name = "dpp_revision")
public class DppRevision {

    @EmbeddedId
    private DppRevisionId id;

    @MapsId("dppId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "dpp_id", nullable = false)
    private LogicalDpp dpp;

    @JoinColumns({
            @JoinColumn(name = "schema_major_version",
                    referencedColumnName = "major_version",
                    nullable = false),
            @JoinColumn(name = "schema_minor_version",
                    referencedColumnName = "minor_version",
                    nullable = false),
            @JoinColumn(name = "subject_type_name",
                    referencedColumnName = "subject_type_name",
                    nullable = false)})
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    private DppSchema dppSchema;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "dpp_document", nullable = false)
    private Map<String, Object> dppDocument;

    @Column(name = "hashed_document", nullable = false)
    private byte[] hashedDocument;

    /**
     * We only use the createdAt field for auditing and logging purposes. It is not part of the DPP revision model as described in the paper.
     */
    @ColumnDefault("now()")
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    /**
     * This method re-verifies Invariant 4 (Payload Integrity).
     * Verifies the integrity of the DPP document by calculating its hash and comparing it to the stored value.
     */
    @PrePersist
    private void verifyHashIntegrity() {
        if (dppDocument == null) {
            return;
        }
        byte[] computedHash = DppUtil.hashDocument(dppDocument);
        if (hashedDocument != null) {
            if (!Arrays.equals(hashedDocument, computedHash)) {
                log.error("Hash integrity violation for DPP {} version {}: provided hash does not match computed payload hash",
                        id != null ? id.getDppId() : "unknown",
                        id != null ? id.getDppVersion() : "unknown");
                throw new IllegalStateException("DPP Revision hash integrity violation: stored hash does not match payload");
            }
        } else {
            hashedDocument = computedHash;
        }
    }

    /**
     * Rejects updates to existing revisions.
     * <p>
     * DPP revisions are append-only artefacts in the formal model. A correction must be represented as a new
     * revision with the next consecutive version number, never as a mutation of an already-persisted row.
     * </p>
     */
    @PreUpdate
    private void rejectUpdate() {
        throw new IllegalStateException("DPP revisions are immutable and must not be updated");
    }

    public Integer getVersion() {
        return id.getDppVersion();
    }
}