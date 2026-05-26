package ch.bfh.generic_dpp_platform.schemas.models;

import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import com.fasterxml.jackson.databind.JsonNode;
import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;

/**
 * <p>
 * This class represents a DPP schema which is cached in the database.
 * The platform itself cannot create new schemas but can retrieve and use them.
 * </p>
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

    @Column(name = "published_at")
    private Instant publishedAt;
}
