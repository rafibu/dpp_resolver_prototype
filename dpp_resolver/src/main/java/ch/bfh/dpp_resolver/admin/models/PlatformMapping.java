package ch.bfh.dpp_resolver.admin.models;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;

/**
 *
 * @author rbu on 20.04.2026
 */
@Getter
@Setter
@Entity
@Table(name = "platform_mapping")
public class PlatformMapping {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id", nullable = false)
    private Long id;

    @Column(name = "platform_name", nullable = false)
    private String platformName;

    @ManyToOne
    @JoinColumn(name = "subject_type_id", nullable = false)
    private SubjectType subjectType;

    /**
     * <p>The abbreviation of the platform name.
     * It is unique within a subject type.
     * It is added at the start of each issued DPP-Id to resolve the URL.</p>
     */
    @Column(name = "abbreviation", nullable = false)
    private String abbreviation;

    /**
     * <p>The URL to the resolution of the platform name.
     * It should have the placeholder {dppId} where the DPP ID should be inserted.
     * The revision is then appended automatically at the end.</p>
     * e.g., https://example.com/dpp/{dppId} → https://example.com/dpp/exa-123abc/2
     */
    @Column(name = "resolution_url", nullable = false)
    private String resolutionUrl;
}
