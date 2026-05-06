package ch.bfh.generic_dpp_platform.dpps.models;

import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import org.hibernate.annotations.ColumnDefault;
import org.jspecify.annotations.NonNull;

import java.time.Instant;
import java.util.LinkedHashSet;
import java.util.Set;

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

    @ColumnDefault("now()")
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @NonNull
    @OneToMany(mappedBy = "dpp")
    private Set<DppRevision> dppRevisions = new LinkedHashSet<>();

}