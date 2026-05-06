package ch.bfh.generic_dpp_platform.schemas.models;

import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import com.fasterxml.jackson.databind.JsonNode;
import jakarta.persistence.*;
import lombok.*;
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
@Builder
@Table(name = "dpp_schema")
@NoArgsConstructor
@AllArgsConstructor
public class DppSchema {

    @EmbeddedId
    private DppSchemaId id;

    @MapsId("subjectTypeName")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "subject_type_name", nullable = false)
    private SubjectType subjectType;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "schema_document", nullable = false, columnDefinition = "jsonb")
    private JsonNode schemaDocument;

    @Column(name = "published_at", nullable = false)
    private Instant publishedAt;
}
