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
 *
 * @author rbu on 20.04.2026
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

    @Column(name = "published_at", nullable = false)
    private Instant publishedAt;
}
