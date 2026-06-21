package ch.bfh.generic_dpp_platform.queries.models;

import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import ch.bfh.generic_dpp_platform.dpps.models.LogicalDpp;
import jakarta.persistence.*;
import jakarta.validation.constraints.NotNull;
import lombok.Getter;
import lombok.Setter;
import org.hibernate.annotations.OnDelete;
import org.hibernate.annotations.OnDeleteAction;

import java.math.BigDecimal;


/**
 * Materialized query fact for the current indexed state of a logical DPP.
 * <p>
 * This entity stores one schema-projected attribute fact for one logical DPP and one query path.
 * It is used as a physical optimization of the paper’s derived query view,
 * allowing indexed predicate queries without reparsing DPP payloads.
 * <p>
 * The authoritative data remains the immutable DPP revision and its schema artefact.
 * The index can be rebuilt from stored payloads and schemas.
 * The subject type is stored redundantly for efficient lookup,
 * and exactly one value field should be set: valueText, valueNumber, or valueBoolean.
 */
@Getter
@Setter
@Entity
@Table(name = "query_attribute_fact")
public class QueryAttributeFact {
    @EmbeddedId
    private QueryAttributeFactId id;

    @MapsId("logicalDppId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @OnDelete(action = OnDeleteAction.CASCADE)
    @JoinColumn(name = "logical_dpp_id", nullable = false)
    private LogicalDpp logicalDpp;

    @NotNull
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "subject_type", nullable = false)
    private SubjectType subjectType;

    @Column(name = "value_text", columnDefinition = "TEXT")
    private String valueText;

    @Column(name = "value_number")
    private BigDecimal valueNumber;

    @Column(name = "value_boolean")
    private Boolean valueBoolean;

    public String getPath() {
        return id.getPath();
    }

    public Object getValue() {
        if (valueText != null) {
            return valueText;
        }
        if (valueNumber != null) {
            return valueNumber;
        }
        return valueBoolean;
    }

}