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
import org.springframework.web.servlet.view.RedirectView;

import java.net.URI;

/**
 * Controller for handling URL resolution requests.
 * Redirects all requests to the dedicated DPP-Platforms making the DPPs platform-independent.
 *
 * @author rbu on 20.04.2026
 */
@Slf4j
@RequiredArgsConstructor
@RestController
public class UrlResolverController {

    private final UrlResolverService urlResolverService;

    /**
     * Resolves a URL based on the provided subject type and issuer-qualified DPP ID.
     * Redirects to the resolved URL if found, or sends a 404 response if the URL could not be resolved.
     *
     * @param subjectType          the type of the subject for which the URL needs to be resolved
     * @param issuerQualifiedDppId the issuer-qualified identifier for the DPP
     * @return a {@code RedirectView} pointing to the resolved URL
     * @throws ResponseStatusException if no URL could be resolved for the given parameters
     */
    @GetMapping("/{subjectType}/{issuerQualifiedDppId}")
    public ResponseEntity<Void> resolveUrl(@PathVariable String subjectType, @PathVariable String issuerQualifiedDppId) {
        log.info("Resolve URL for SubjectType: {}, DPPId: {}", subjectType, issuerQualifiedDppId);
        try {
            String resolvedUrl = urlResolverService.resolveUrl(subjectType, issuerQualifiedDppId);
            if (resolvedUrl == null) {
                throw new ResponseStatusException(HttpStatus.NOT_FOUND, "DPP with this DPPId does not exist");
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
     * Resolves a URL based on the provided subject type, issuer-qualified DPP ID, and a specific revision number.
     * Redirects to the resolved URL if found, or sends a 404 response if the URL could not be resolved.
     *
     * @param subjectType          the type of the subject for which the URL needs to be resolved
     * @param issuerQualifiedDppId the issuer-qualified identifier for the DPP
     * @param revision             the revision number to be used in the URL resolution
     * @return a {@code RedirectView} pointing to the resolved URL
     * @throws ResponseStatusException if no URL could be resolved for the given parameters
     */
    @GetMapping("/{subjectType}/{issuerQualifiedDppId}/{revision}")
    public ResponseEntity<Void> resolveUrlWithRevision(@PathVariable String subjectType, @PathVariable String issuerQualifiedDppId, @PathVariable String revision) {
        log.info("Resolve URL for SubjectType: {}, DPPId: {}, Revision: {}", subjectType, issuerQualifiedDppId, revision);
        try {
            String resolvedUrl = urlResolverService.resolveUrl(subjectType, issuerQualifiedDppId, revision);
            if (resolvedUrl == null) {
                throw new ResponseStatusException(HttpStatus.NOT_FOUND, "DPP with this DPPId and revision does not exist");
            }
            return ResponseEntity.status(HttpStatus.FOUND)
                    .location(URI.create(resolvedUrl))
                    .header("X-DPP-Subject-Type", subjectType)
                    .header("X-DPP-Resolved-Revision", String.valueOf(revision))
                    .header("X-DPP-Reference-Type", "HARD")
                    .build();
        } catch (IllegalArgumentException e) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, e.getMessage());
        }
    }
}
