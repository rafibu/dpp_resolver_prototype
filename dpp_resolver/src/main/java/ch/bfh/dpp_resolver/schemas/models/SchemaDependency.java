package ch.bfh.dpp_resolver.schemas.models;

import ch.bfh.dpp_resolver.admin.models.SubjectType;
import jakarta.persistence.*;
import lombok.*;

import java.io.Serializable;

@Getter
@Setter
@Entity
@Table(name = "schema_dependency")
@NoArgsConstructor
@AllArgsConstructor
public class SchemaDependency {

    @EmbeddedId
    private SchemaDependencyId id;

    @MapsId("fromSubjectTypeId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "from_subject_type_id", nullable = false)
    private SubjectType fromSubjectType;

    @MapsId("toSubjectTypeId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "to_subject_type_id", nullable = false)
    private SubjectType toSubjectType;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumns({
        @JoinColumn(name = "schema_major", referencedColumnName = "major_version", insertable = false, updatable = false),
        @JoinColumn(name = "schema_minor", referencedColumnName = "minor_version", insertable = false, updatable = false),
        @JoinColumn(name = "from_subject_type_id", referencedColumnName = "subject_type_id", insertable = false, updatable = false)
    })
    private DppSchema schema;

    @Embeddable
    @Getter
    @Setter
    @EqualsAndHashCode
    @NoArgsConstructor
    @AllArgsConstructor
    public static class SchemaDependencyId implements Serializable {
        @Column(name = "from_subject_type_id")
        private Long fromSubjectTypeId;

        @Column(name = "to_subject_type_id")
        private Long toSubjectTypeId;

        @Column(name = "schema_major")
        private Integer schemaMajor;

        @Column(name = "schema_minor")
        private Integer schemaMinor;
    }
}
