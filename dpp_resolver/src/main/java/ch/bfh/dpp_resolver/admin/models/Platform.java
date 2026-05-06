package ch.bfh.dpp_resolver.admin.models;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;

import java.util.List;

/**
 *
 * @author rbu on 20.04.2026
 */
@Getter
@Setter
@Entity
@Table(name = "platform")
public class Platform {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id", nullable = false)
    private Long id;

    @Column(name = "platform_name", nullable = false)
    private String platformName;

    @ManyToMany(fetch = FetchType.LAZY)
    @JoinTable(name = "platform_mapping", joinColumns = @JoinColumn(name = "platform_id"), inverseJoinColumns = @JoinColumn(name = "subject_type_id"))
    private List<SubjectType> subjectTypes;

    /**
     * <p>The abbreviation of the platform name.
     * It is unique.
     * It is added at the start of each issued DPP-Id to resolve the URL.</p>
     */
    @Column(name = "abbreviation", nullable = false, unique = true)
    private String abbreviation;

    /**
     * <p>The URL to the resolution of the platform name.
     * It should have the placeholder {dppId} where the DPP ID should be inserted.<br>
     * It can optionally have a placeholder {subjectType} where the subject type abbreviation should be inserted.<br>
     * It can optionally have a placeholder {major} and {minor} where the major and minor version numbers should be inserted.<br>
     * The revision is then appended automatically at the end.</p>
     * e.g., https://example.com/dpp/{subjectType}/{dppId}/{major}.{minor} → https://example.com/dpp/subject/exa-123abc/2.1
     */
    @Column(name = "resolution_url", nullable = false)
    private String resolutionUrl;
}
