package ch.bfh.dpp_resolver.schemas.models;

import ch.bfh.dpp_resolver.admin.models.SubjectType;
import com.fasterxml.jackson.databind.JsonNode;
import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;

/**
 * One schema artefact in the authoritative schema set of the resolver state (Definition 6).
 *
 * <p>Corresponds to Definition 3 (Schema artefact): a tuple of subject type, validator
 * predicate (here the {@link #schemaDocument} JSON Schema document), and version (major,
 * minor). The schema set is the single source of truth for all schema artefacts in the
 * ecosystem. DPP platforms store a subset of this set in their local caches and reference
 * schemas by exact version in every revision (Invariant I3).</p>
 *
 * <p>Published schemas are immutable: once added to the authoritative set they are never
 * removed. This guarantees that historical revisions remain interpretable
 * against the schema version under which they were issued, even after newer versions are
 * published (Invariant I5 combined with I3).</p>
 */
@Getter
@Setter
@Entity
@Table(name = "dpp_schema")
public class DppSchema {

    @EmbeddedId
    private DppSchemaId id;

    @MapsId("subjectTypeId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "subject_type_id", nullable = false)
    private SubjectType subjectType;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "schema_document", nullable = false, columnDefinition = "jsonb")
    private JsonNode schemaDocument;

    /**
     * The timestamp at which this schema was published in the authoritative set.
     * It is not part of the formal model. This is mostly useful for debugging and auditing purposes.
     */
    @Column(name = "published_at", nullable = false)
    private Instant publishedAt;


    @PreRemove
    public void preRemove() {
        throw new IllegalStateException("Cannot remove a DPP schema");
    }

    @PreUpdate
    public void preUpdate() {
        throw new IllegalStateException("Cannot update a DPP schema");
    }
}
