package ch.bfh.dpp_resolver.url_resolver.services;

import ch.bfh.dpp_resolver.admin.models.Platform;
import ch.bfh.dpp_resolver.admin.models.SubjectType;
import ch.bfh.dpp_resolver.admin.repositories.PlatformRepository;
import ch.bfh.dpp_resolver.admin.repositories.SubjectTypeRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

/**
 * Implements the read-only {@code resolve} operation from the paper's transition system
 * and the registry lookup defined in Definition 11.
 *
 * <p>The resolver state consists of the authoritative schema set and the resolver registry
 * (Definition 6). The registry is a total function from issuers to hosting platforms
 * (Definition 10). This service implements the two-step lookup of Definition 11: it
 * extracts the issuer from the DPP identity, locates the hosting platform in the registry,
 * and constructs the redirect URL for the calling platform to follow.</p>
 *
 * <p>The resolver returns a 302 redirect rather than the revision payload. The calling
 * platform follows the redirect to fetch the revision directly from the hosting platform.
 * This preserves the federated architecture: the resolver knows where each DPP is hosted
 * but does not replicate revision data.</p>
 *
 * @see ch.bfh.dpp_resolver.url_resolver.controllers.UrlResolverController
 */
@Service
@RequiredArgsConstructor
public class UrlResolverService {

    private final PlatformRepository platformRepository;
    private final SubjectTypeRepository subjectTypeRepository;

    /**
     * Resolves a soft federated reference to a redirect URL (Definition 9, soft mode).
     *
     * <p>Corresponds to Case 3 of Definition 11 (Resolution): the reference has no version
     * component, so the resolver routes to the hosting platform without pinning a revision.
     * The platform returns its current revision for the logical DPP.</p>
     *
     * @param subjectType the subject type component of the DPP identity
     * @param dppId       the issuer-qualified DPP identifier in format {@code issuer-localId}
     * @return the redirect URL, or {@code null} if the issuer is not registered (Case 1)
     */
    public String resolveUrl(String subjectType, String dppId) {
        return resolveUrl(subjectType, dppId, null);
    }

    /**
     * Resolves a federated reference to a redirect URL (Definition 11).
     *
     * <p>The issuer component of the DPP identity is extracted and looked up in the
     * resolver registry (Definition 10). If the issuer is not registered, {@code null}
     * is returned corresponding to Case 1 of Definition 11. Otherwise a redirect URL is
     * constructed pointing to the hosting platform.</p>
     *
     * <p>When {@code revisionVersion} is non-null this is a hard reference (Definition 9):
     * the revision version is appended to the platform URL so the caller receives the exact
     * revision (Case 2 of Definition 11). When {@code null} this is a soft reference and
     * the platform returns its current revision (Case 3).</p>
     *
     * <p>This service adds a subject-type check beyond Definition 10: it verifies that the
     * registered platform has declared support for the requested subject type. This is a
     * prototype-level guard and is not part of the formal registry model.</p>
     *
     * @param subjectType     the subject type component of the DPP identity
     * @param dppId           the issuer-qualified DPP identifier in format {@code issuer-localId}
     * @param revisionVersion the DPP revision version as a positive integer string, or
     *                        {@code null} for a soft reference
     * @return the redirect URL, or {@code null} if the issuer is not registered or the subject
     *         type is not supported by the registered platform
     * @throws IllegalArgumentException if the DPP ID has no issuer prefix or the revision
     *                                  version is not a positive integer
     */
    public String resolveUrl(String subjectType, String dppId, String revisionVersion) {
        String issuer = extractIssuer(dppId);

        Integer version = null;
        if (revisionVersion != null) {
            try {
                version = Integer.parseInt(revisionVersion.trim());
            } catch (NumberFormatException e) {
                throw new IllegalArgumentException("Revision version must be a positive integer");
            }
            if (version <= 0) {
                throw new IllegalArgumentException("Revision version must be a positive integer");
            }
        }

        SubjectType subject = subjectTypeRepository.findByName(subjectType).orElseThrow();
        Platform mapping = platformRepository.findByAbbreviation(issuer).orElse(null);

        if (mapping == null) {
            // Case 1 of Definition 11: issuer not in the registry.
            return null;
        }

        // Prototype extension beyond Definition 10: verify the registered platform declared
        // support for this subject type.
        if (!mapping.getSubjectTypes().contains(subject)) {
            return null;
        }

        return buildUrl(mapping.getResolutionUrl(), dppId, subjectType, version);
    }

    /**
     * Extracts the issuer component from an issuer-qualified DPP identifier.
     *
     * <p>Per the identity format in Definition 1, a DPP identity includes issuer, subject
     * type, and local identifier. The issuer-qualified DPP ID combines issuer and local
     * identifier as {@code issuer-localId}. The issuer is the prefix before the first
     * {@code -}; the local identifier may itself contain {@code -} (for example when it
     * is a UUID).</p>
     *
     * @param dppId the issuer-qualified DPP identifier
     * @return the issuer component
     * @throws IllegalArgumentException if the DPP ID contains no {@code -} separator
     */
    private static String extractIssuer(String dppId) {
        int dashIndex = dppId.indexOf('-');
        if (dashIndex <= 0) {
            throw new IllegalArgumentException("DPP ID must be in format 'issuer-localId'");
        }
        return dppId.substring(0, dashIndex);
    }

    /**
     * Constructs the redirect URL from the platform's URL template by substituting DPP
     * identity components and appending the revision version when present.
     *
     * <p>Supported placeholders in the template:</p>
     * <ul>
     *   <li>{@code {dppId}} (required): replaced with the issuer-qualified DPP identifier.</li>
     *   <li>{@code {subjectType}} (optional): replaced with the subject type name.</li>
     *   <li>{@code {revision}} (optional): replaced with the DPP revision version integer;
     *       if absent and a revision is requested, the version is appended as a path segment.</li>
     * </ul>
     *
     * @param template        the URL template from the resolver registry entry
     * @param dppId           the issuer-qualified DPP identifier
     * @param subjectType     the subject type
     * @param revisionVersion the DPP revision version, or {@code null}
     * @return the fully resolved redirect URL
     * @throws IllegalArgumentException if the template does not contain {@code {dppId}}
     */
    private static String buildUrl(String template, String dppId, String subjectType, Integer revisionVersion) {
        if (!template.contains("{dppId}")) {
            throw new IllegalArgumentException("Resolution URL template must contain {dppId} placeholder");
        }

        String url = template
                .replace("{dppId}", dppId)
                .replace("{subjectType}", subjectType);

        if (revisionVersion != null) {
            if (url.contains("{revision}")) {
                url = url.replace("{revision}", revisionVersion.toString());
            } else {
                url = url + "/" + revisionVersion;
            }
        }

        return url;
    }
}
