package ch.bfh.dpp_resolver.url_resolver.services;

import ch.bfh.dpp_resolver.admin.models.Platform;
import ch.bfh.dpp_resolver.admin.models.SubjectType;
import ch.bfh.dpp_resolver.admin.repositories.PlatformRepository;
import ch.bfh.dpp_resolver.admin.repositories.SubjectTypeRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

/**
 *
 * @author rbu on 21.04.2026
 */
@Service
@RequiredArgsConstructor
public class UrlResolverService {

    private final PlatformRepository platformRepository;
    private final SubjectTypeRepository subjectTypeRepository;

    /**
     * Resolves a URL based on the provided subject type and DPPId, delegating to the
     * full method with an optional revision number set to null.
     *
     * @param subjectType the name of the subject type to be resolved
     * @param dppId       the identifier used for mapping, in the format 'issuer-qualifiedDppId'
     * @return the resolved URL as a string, or null if no mapping exists for the given combination of inputs
     */
    public String resolveUrl(String subjectType, String dppId) {
        return resolveUrl(subjectType, dppId, null);
    }

    /**
     * Resolves a URL based on the provided subject type, DPPId, and optional revision number.
     * This method fetches the corresponding {@link SubjectType} and uses a mapping to construct
     * a resolution URL.
     *
     * @param subjectType the name of the subject type to be resolved
     * @param dppId       the identifier used for mapping, in the format 'issuer-qualifiedDppId'
     * @param revision    the optional revision number to be appended to the URL, or null if no revision is provided
     * @return the resolved URL as a string, or null if no mapping exists for the given combination of inputs
     */
    public String resolveUrl(String subjectType, String dppId, String revision) {

        String issuer = extractIssuer(dppId);

        Integer major = null, minor = null;
        if (revision != null) {
            String[] parts = revision.split("[./\\\\]");
            if (parts.length > 2) {
                throw new IllegalArgumentException("Revision must be in format 'major.minor' or 'major/minor'");
            }
            if (parts.length >= 1) {
                major = Integer.parseInt(parts[0].trim());
            }
            if (parts.length == 2) {
                minor = Integer.parseInt(parts[1].trim());
            }
        }

        SubjectType subject = subjectTypeRepository.findByName(subjectType).orElseThrow();

        Platform mapping = platformRepository.findByAbbreviation(issuer).orElse(null);

        if (mapping == null) {
            return null;
        }

        if (!mapping.getSubjectTypes().contains(subject)) {
            return null;
        }

        return createUrl(mapping, dppId, subjectType, major, minor);
    }

    /**
     * Extracts the issuer from the DPPId.
     * We assume that the issuer is the first part of the DPPId.
     *
     * @param dppId the DPPId in format issuer-qualifiedDppId
     * @return the issuer abbreviation string
     */
    private static String extractIssuer(String dppId) {
        String[] splitDppId = dppId.split("-");

        if (splitDppId.length != 2) {
            throw new IllegalArgumentException("DPPId must be in format 'issuer-qualifiedDppId'");
        }

        return splitDppId[0];
    }

    private static String createUrl(Platform mapping, String dppId, String subjectType, Integer major, Integer minor) {
        String baseUrl = mapping.getResolutionUrl();
        if (!baseUrl.contains("{dppId}")) {
            throw new IllegalArgumentException("Resolution URL must contain {dppId} placeholder");
        }
        String resolvedUrl = baseUrl
                .replace("{dppId}", dppId)
                .replace("{subjectType}", subjectType);

        if (major != null) {
            if (baseUrl.contains("{major}")) {
                resolvedUrl = resolvedUrl.replace("{major}", major.toString());
                if (minor != null) {
                    resolvedUrl = resolvedUrl.replace("{minor}", minor.toString());
                } else {
                    resolvedUrl = resolvedUrl.replace(".{minor}", "").replace("{minor}", "");
                }
            } else {
                resolvedUrl = resolvedUrl + "/" + major + (minor != null ? "." + minor : "");
            }
        }

        return resolvedUrl;
    }
}
