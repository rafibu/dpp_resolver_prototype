package ch.bfh.generic_dpp_platform.admin.models;

import jakarta.persistence.*;
import lombok.*;

/**
 *
 * @author rbu on 21.04.2026
 */
@Getter
@Setter
@Entity
@Table(name = "subject_type")
@Builder
@NoArgsConstructor
@AllArgsConstructor
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
