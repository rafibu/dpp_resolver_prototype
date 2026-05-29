package ch.bfh.dpp_resolver.admin.controllers;

import ch.bfh.dpp_resolver.admin.dto.PlatformMappingDTO;
import ch.bfh.dpp_resolver.admin.services.PlatformMappingService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.NoSuchElementException;

/**
 * HTTP controller for resolver registry management.
 *
 * <p>Exposes the {@code registerIssuer} and {@code migrate}
 * operations through a single upsert endpoint. When the issuer
 * identified by {@code issuerId} is not yet in the resolver registry (Definition 10),
 * a {@code POST /admin/platforms} request registers it ({@code registerIssuer}).
 * When the issuer is already registered, the same request updates its platform mapping
 * ({@code migrate}).</p>
 *
 * <p>Query endpoints return the current state of the registry for monitoring and
 * federation discovery by the Factory and Frontend components.</p>
 */
@Slf4j
@RequiredArgsConstructor
@RestController
@RequestMapping("/admin/platforms")
public class PlatformController {

    private final PlatformMappingService platformMappingService;

    /**
     * Returns all resolver registry entries.
     *
     * <p>Returns every issuer-to-platform mapping currently in the resolver registry
     * (Definition 10). Used by the Factory and Frontend for federation discovery.</p>
     *
     * @return all platform mappings with HTTP 200
     */
    @GetMapping
    public ResponseEntity<PlatformMappingDTO[]> getAllPlatformMappings() {
        log.info("GET all PlatformMappings");
        return ResponseEntity.ok(platformMappingService.findAll().toArray(PlatformMappingDTO[]::new));
    }

    /**
     * Returns all registry entries for a given subject type.
     *
     * @param subjectType the subject type name to filter by
     * @return matching platform mappings, or 404 if the subject type is unknown
     */
    @GetMapping("/{subjectType}")
    public ResponseEntity<PlatformMappingDTO[]> getPlatformMappings(@PathVariable String subjectType) {
        log.info("GET PlatformMappings for SubjectType: {}", subjectType);
        try {
            return ResponseEntity.ok(platformMappingService.findAllBySubjectType(subjectType).toArray(PlatformMappingDTO[]::new));
        } catch (NoSuchElementException e) {
            log.error("SubjectType {} not found", subjectType);
            return ResponseEntity.notFound().build();
        }
    }

    /**
     * Registers a new issuer or updates an existing issuer's platform mapping.
     *
     * <p>When the issuer named in {@code platformMappingDTO.issuerId} is not yet in the
     * resolver registry, this implements the {@code registerIssuer} operation:<br>
     * it adds a new entry mapping the issuer to its hosting platform.<br>
     * When the issuer is already registered, this implements the {@code migrate} operation:<br>
     * it updates the registry entry to point to the new hosting platform.</p>
     *
     * <p>The {@code resolutionUrl} field contains the URL template used by the resolver
     * to construct redirect targets for resolution requests (Definition 11).</p>
     *
     * @param platformMappingDTO the issuer registration or migration request
     * @return the saved registry entry with HTTP 201, or 400 on validation failure
     */
    @PostMapping
    public ResponseEntity<PlatformMappingDTO> createNewPlatformMapping(@RequestBody PlatformMappingDTO platformMappingDTO) {
        log.info("POST new PlatformMapping: {}", platformMappingDTO);
        try {
            return ResponseEntity.status(HttpStatus.CREATED).body(platformMappingService.save(platformMappingDTO));
        } catch (NoSuchElementException e) {
            log.error("PlatformMapping could not be saved", e);
            throw new IllegalArgumentException(e);
        }
    }
}
