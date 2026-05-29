package ch.bfh.dpp_resolver.url_resolver.controllers;

import ch.bfh.dpp_resolver.url_resolver.services.UrlResolverService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.net.URI;

/**
 * HTTP controller for the resolver's {@code resolve} operation.
 *
 * <p>Implements Definition 11 (Resolution) over HTTP by returning 302 redirects to the
 * hosting platform. The URL path structure {@code /{subjectType}/{issuerQualifiedDppId}}
 * encodes the logical DPP identity (Definition 1). The calling platform follows the
 * redirect to fetch the revision payload directly from the hosting platform, keeping
 * the resolver free of revision data.</p>
 *
 * <p>The response encodes the reference mode (Definition 9) in a custom header:</p>
 * <ul>
 *   <li>{@code X-DPP-Reference-Type: SOFT} for unversioned requests (soft reference).</li>
 *   <li>{@code X-DPP-Reference-Type: HARD} for versioned requests (hard reference).</li>
 * </ul>
 *
 * <p>DPP platforms call these endpoints during the hard-resolvability check of
 * Invariant I7 and follow the redirect to fetch the exact revision from the
 * hosting platform.</p>
 */
@Slf4j
@RequiredArgsConstructor
@RestController
public class UrlResolverController {

    private final UrlResolverService urlResolverService;

    /**
     * Resolves a soft federated reference (Definition 9) to a hosting-platform redirect.
     *
     * <p>Corresponds to Case 3 of Definition 11: the reference identifies a logical DPP
     * without pinning a specific revision. The platform at the redirect target returns
     * its current revision for the DPP.</p>
     *
     * @param subjectType          the subject type component of the DPP identity
     * @param issuerQualifiedDppId the issuer-qualified DPP identifier in format {@code issuer-localId}
     * @return 302 redirect to the hosting platform, 404 if the issuer is not registered,
     *         400 if the DPP ID format is invalid
     */
    @GetMapping("/{subjectType}/{issuerQualifiedDppId}")
    public ResponseEntity<Void> resolveUrl(@PathVariable String subjectType, @PathVariable String issuerQualifiedDppId) {
        log.info("Resolve URL for SubjectType: {}, DPPId: {}", subjectType, issuerQualifiedDppId);
        try {
            String resolvedUrl = urlResolverService.resolveUrl(subjectType, issuerQualifiedDppId);
            if (resolvedUrl == null) {
                throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Issuer not registered or subject type not supported");
            }
            return ResponseEntity.status(HttpStatus.FOUND)
                    .location(URI.create(resolvedUrl))
                    .header("X-DPP-Subject-Type", subjectType)
                    .header("X-DPP-Reference-Type", "SOFT")
                    .build();
        } catch (IllegalArgumentException e) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, e.getMessage());
        }
    }

    /**
     * Resolves a hard federated reference (Definition 9) to a hosting-platform redirect.
     *
     * <p>Corresponds to Case 2 of Definition 11: the reference pinpoints an exact revision
     * of a logical DPP. The revision version is appended to the redirect URL so the
     * calling platform receives the specific immutable revision.</p>
     *
     * <p>This endpoint is called by DPP platforms during Invariant I7 enforcement: before
     * committing a new revision that contains hard references, the platform follows these
     * redirects to confirm each referenced revision exists.</p>
     *
     * @param subjectType          the subject type component of the DPP identity
     * @param issuerQualifiedDppId the issuer-qualified DPP identifier in format {@code issuer-localId}
     * @param revisionVersion      the DPP revision version as a positive integer
     * @return 302 redirect to the exact revision on the hosting platform, 404 if the issuer
     *         is not registered, 400 if the DPP ID or revision format is invalid
     */
    @GetMapping("/{subjectType}/{issuerQualifiedDppId}/{revisionVersion}")
    public ResponseEntity<Void> resolveUrlWithRevision(
            @PathVariable String subjectType,
            @PathVariable String issuerQualifiedDppId,
            @PathVariable String revisionVersion) {
        log.info("Resolve URL for SubjectType: {}, DPPId: {}, Revision: {}", subjectType, issuerQualifiedDppId, revisionVersion);
        try {
            String resolvedUrl = urlResolverService.resolveUrl(subjectType, issuerQualifiedDppId, revisionVersion);
            if (resolvedUrl == null) {
                throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Issuer not registered or subject type not supported");
            }
            return ResponseEntity.status(HttpStatus.FOUND)
                    .location(URI.create(resolvedUrl))
                    .header("X-DPP-Subject-Type", subjectType)
                    .header("X-DPP-Resolved-Revision", revisionVersion)
                    .header("X-DPP-Reference-Type", "HARD")
                    .build();
        } catch (IllegalArgumentException e) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, e.getMessage());
        }
    }
}
