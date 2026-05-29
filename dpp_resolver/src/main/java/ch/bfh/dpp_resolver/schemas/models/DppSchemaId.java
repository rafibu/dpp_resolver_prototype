package ch.bfh.dpp_resolver.schemas.models;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import lombok.*;

/**
 * Composite identifier of a schema artefact (Definition 3).
 *
 * <p>A schema artefact is uniquely identified by the subject type it governs and its
 * (major, minor) version within that subject type. Two schema artefacts with the same
 * subject type and version are the same artefact; two with the same subject type but
 * different versions are distinct artefacts that may stand in a backward-compatibility
 * relation (Definition 15, Definition 16).</p>
 */
@Getter
@Setter
@EqualsAndHashCode
@Embeddable
@AllArgsConstructor
@NoArgsConstructor
public class DppSchemaId {

    @Column(name = "major_version", nullable = false)
    private Integer majorVersion;

    @Column(name = "minor_version", nullable = false)
    private Integer minorVersion;

    @Column(name = "subject_type_id", nullable = false)
    private Long subjectTypeId;

    public boolean invalid() {
        return majorVersion == null || minorVersion == null || subjectTypeId == null
                || majorVersion <= 0 || minorVersion < 0;
    }

    @Override
    public String toString() {
        return String.format("%s v%s.%s", subjectTypeId, majorVersion, minorVersion);
    }
}
