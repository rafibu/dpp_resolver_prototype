package ch.bfh.dpp_resolver.admin.models;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;

import java.util.List;

/**
 * One entry in the resolver registry (Definition 10 of the formal model).
 *
 * <p>Maps an issuer identifier ({@link #abbreviation}) to the URL template of the platform
 * that currently hosts its DPPs. Created by the {@code registerIssuer} operation
 * via {@code POST /admin/platforms/register} and updated by {@code migrate} via
 * {@code POST /admin/platforms/{issuerId}/migrate}.</p>
 *
 * @see ch.bfh.dpp_resolver.admin.controllers.PlatformController
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

    /**
     * Prototype extension beyond Definition 10: subject types the issuer declares support for.
     * The resolver rejects resolution requests for subject types absent from this list.
     */
    @ManyToMany(fetch = FetchType.LAZY)
    @JoinTable(name = "platform_mapping", joinColumns = @JoinColumn(name = "platform_id"), inverseJoinColumns = @JoinColumn(name = "subject_type_id"))
    private List<SubjectType> subjectTypes;

    /**
     * Issuer identifier (Definition 10): prefix of all DPP IDs issued by this platform.
     * The resolver extracts this prefix from the DPP ID to locate the correct registry entry.
     */
    @Column(name = "abbreviation", nullable = false, unique = true)
    private String abbreviation;

    /**
     * URL template for resolving DPPs hosted by this issuer.
     *
     * <p>Required placeholder: {@code {dppId}} (replaced with the issuer-qualified DPP
     * identifier). Optional placeholders:</p>
     * <ul>
     *   <li>{@code {subjectType}}: replaced with the subject type name.</li>
     *   <li>{@code {revision}}: replaced with the DPP revision version integer; if absent,
     *       the version is appended as a path segment.</li>
     * </ul>
     * Example: {@code http://platform-a:8081/dpps/{dppId}} resolves to
     * {@code http://platform-a:8081/dpps/issuerA-product-001/2} when revision 2 is
     * requested.
     */
    @Column(name = "resolution_url", nullable = false)
    private String resolutionUrl;
}
