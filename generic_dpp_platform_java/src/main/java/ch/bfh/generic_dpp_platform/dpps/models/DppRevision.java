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

    @ColumnDefault("now()")
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @PrePersist
    @PreUpdate
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

    public Integer getVersion() {
        return id.getDppVersion();
    }
}