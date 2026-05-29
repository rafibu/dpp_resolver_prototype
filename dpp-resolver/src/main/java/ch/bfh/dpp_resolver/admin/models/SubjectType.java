package ch.bfh.dpp_resolver.admin.models;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;

import java.util.ArrayList;
import java.util.List;

/**
 * One element of the set of subject types used throughout the formal model.
 *
 * <p>Subject types correspond to the set referenced in Definitions 1, 3, 8, and 13.
 * A subject type denotes a product domain (e.g. {@code pv_module}, {@code battery},
 * {@code inverter}). Each schema artefact (Definition 3) governs exactly one subject
 * type. The schema dependency graph (Definition 13) has subject types as vertices.</p>
 *
 * <p>Subject types are managed by the resolver and must exist before schemas for that
 * type can be published or before issuers can be registered for that type.</p>
 */
@Getter
@Setter
@Entity
@Table(name = "subject_type")
public class SubjectType {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id", nullable = false)
    private Long id;

    @Column(name = "name", nullable = false)
    private String name;
    @Column(name = "description")
    private String description;

    @ManyToMany(mappedBy = "subjectTypes")
    private List<Platform> platforms = new ArrayList<>();

}
