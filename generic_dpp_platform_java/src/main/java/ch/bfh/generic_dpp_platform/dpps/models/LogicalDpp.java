package ch.bfh.generic_dpp_platform.dpps.models;

import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import org.jspecify.annotations.NonNull;

import java.util.LinkedHashSet;
import java.util.Set;

/**
 * Represents a logical Digital Product Passport (DPP) entity in the system. A LogicalDpp serves
 * as an abstraction for a DPP, encapsulating its metadata. Each logical DPP can have multiple revisions.
 * <br>
 * Key Features:
 * - Identified by a unique `dppId`, serving as the primary key.
 * - Linked to a specific Subject Type
 * - Maintains a collection of associated revision instances, representing various
 *   revisions of the DPP.
 * <br>
 * Entity Relationships:
 * - Many-to-One relationship with the `SubjectType` entity, specifying the type of
 *   the subject associated with this DPP.
 * - One-to-Many relationship with the `DppRevision` entity, supporting a logical
 *   grouping of its revisions.
 * <br>
 * Constraints:
 * - The `dppId` is mandatory and serves as a unique identifier for each LogicalDpp.
 * - The `subjectType` association is required and cannot be null.
 * - The set of `dppRevisions` is initialized as empty and cannot be null.
 */
@Getter
@Setter
@Entity
@Table(name = "logical_dpp")
public class LogicalDpp {
    @Id
    @Column(name = "dpp_id", nullable = false)
    private String dppId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "subject_type_name", nullable = false)
    private SubjectType subjectType;

    @NonNull
    @OneToMany(mappedBy = "dpp")
    private Set<DppRevision> dppRevisions = new LinkedHashSet<>();

}