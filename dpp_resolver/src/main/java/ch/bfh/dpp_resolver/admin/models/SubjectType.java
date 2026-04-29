package ch.bfh.dpp_resolver.admin.models;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;

/**
 *
 * @author rbu on 17.04.2026
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
}
