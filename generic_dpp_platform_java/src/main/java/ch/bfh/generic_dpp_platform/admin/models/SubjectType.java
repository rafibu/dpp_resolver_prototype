package ch.bfh.generic_dpp_platform.admin.models;

import jakarta.persistence.*;
import lombok.*;

/**
 * All Subject Types which are supported by the platform must be stored in this table.
 * Their name is used as the identifier and must match the name in the resolver exactly.
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
    @Column(name = "name", nullable = false)
    private String name;

    @Column(name = "description")
    private String description;
}
