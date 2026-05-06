package ch.bfh.generic_dpp_platform.dpps.models;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import lombok.*;

import java.io.Serializable;

/**
 * Composite key for referenced (external) DPP revisions.
 */
@Embeddable
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class ReferencedDppRevisionId implements Serializable {

    @Column(name = "dpp_id", nullable = false)
    private String dppId;

    @Column(name = "dpp_version", nullable = false)
    private Integer dppVersion;
}
