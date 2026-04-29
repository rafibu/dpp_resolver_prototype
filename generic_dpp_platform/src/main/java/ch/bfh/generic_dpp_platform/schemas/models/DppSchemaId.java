package ch.bfh.generic_dpp_platform.schemas.models;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import lombok.*;

/**
 * Composite identifier of a DPP schema artifact
 *
 * <p>A schema is uniquely identified by the subject type it defines and its
 * semantic version within that subject type.</p>
 *
 * @author rbu on 20.04.2026
 */
@Getter
@Setter
@EqualsAndHashCode
@Embeddable
@Builder
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
