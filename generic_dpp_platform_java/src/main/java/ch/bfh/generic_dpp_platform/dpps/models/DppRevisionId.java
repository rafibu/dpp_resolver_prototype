package ch.bfh.generic_dpp_platform.dpps.models;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import lombok.*;

import java.io.Serial;
import java.io.Serializable;

/**
 * Composite key for DPP revisions.
 */
@Getter
@Setter
@EqualsAndHashCode
@Embeddable
@AllArgsConstructor
@NoArgsConstructor
public class DppRevisionId implements Serializable {
    @Serial
    private static final long serialVersionUID = -6184889338475830624L;

    @Column(name = "dpp_version", nullable = false)
    private Integer dppVersion;

    @Column(name = "dpp_id", nullable = false)
    private String dppId;


}