package ch.bfh.dpp_resolver.admin.controllers;

import ch.bfh.dpp_resolver.admin.dto.PlatformMappingDTO;
import ch.bfh.dpp_resolver.admin.dto.PlatformMigrationRequestDTO;
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
 * <p>Exposes separate HTTP endpoints for the {@code registerIssuer} and
 * {@code migrate} operations. Registering creates a new issuer-to-platform
 * registry entry; migrating updates the hosting platform for an existing issuer
 * without changing the issuer's declared subject types.
 * Adding subject-type support extends an existing issuer mapping without
 * registering or migrating it.</p>
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
     * Registers a new issuer in the resolver registry.
     *
     * <p>This endpoint operationalizes {@code registerIssuer}. It creates one new
     * Definition 10 registry entry for {@code platformMappingDTO.issuerId}, maps it
     * to the provided platform and resolution URL, and stores the issuer's declared
     * subject types. Existing issuers are rejected. Callers must use the migration
     * endpoint when moving an already registered issuer.</p>
     *
     * <p>The {@code resolutionUrl} field contains the URL template used by the resolver
     * to construct redirect targets for resolution requests (Definition 11).</p>
     *
     * @param platformMappingDTO the issuer registration request
     * @return the saved registry entry with HTTP 201, or 400 on validation failure
     */
    @PostMapping("/register")
    public ResponseEntity<PlatformMappingDTO> registerIssuer(@RequestBody PlatformMappingDTO platformMappingDTO) {
        log.info("Register new issuer: {}", platformMappingDTO);
        try {
            return ResponseEntity.status(HttpStatus.CREATED).body(platformMappingService.registerIssuer(platformMappingDTO));
        } catch (NoSuchElementException e) {
            log.error("PlatformMapping could not be saved", e);
            throw new IllegalArgumentException(e);
        }
    }

    /**
     * Migrates an existing issuer to another hosting platform.
     *
     * <p>This endpoint operationalizes {@code migrate}. It updates the platform name
     * and resolution URL of the existing issuer entry while preserving that issuer's
     * subject type set.
     * The target platform must already be known to the resolver,
     * which prevents migration from accidentally creating a new issuer or platform
     * mapping.</p>
     *
     * @param issuerId   the issuerId to migrate
     * @param requestDTO the target platform name and new resolution URL
     * @return the updated registry entry with HTTP 200
     */
    @PostMapping("/{issuerId}/migrate")
    public ResponseEntity<PlatformMappingDTO> migrateIssuer(@PathVariable String issuerId, @RequestBody PlatformMigrationRequestDTO requestDTO) {
        log.info("Migrate issuer: {} to platform: {}", issuerId, requestDTO);
        try {
            return ResponseEntity.ok(platformMappingService.migrateIssuer(issuerId, requestDTO));
        } catch (NoSuchElementException e) {
            log.error("Migration failed for issuerId: {}, error: {}", issuerId, e.getMessage());
            throw new IllegalArgumentException(e);
        }
    }

    /**
     * Adds subject-type support to an existing issuer mapping.
     *
     * <p>This endpoint extends the issuer's declared subject-type set while
     * preserving its platform name and resolution URL. It is intentionally
     * separate from {@code registerIssuer} and {@code migrate}: it cannot create a
     * new issuer mapping and cannot move an issuer to another platform.</p>
     *
     * @param issuerId    the existing issuer mapping to extend
     * @param subjectType the existing subject type to add to the issuer mapping
     * @return the updated registry entry with HTTP 200
     */
    @PostMapping("/{issuerId}/subject-types/{subjectType}")
    public ResponseEntity<PlatformMappingDTO> addSubjectTypeSupport(
            @PathVariable String issuerId,
            @PathVariable String subjectType
    ) {
        log.info("Add subject type support: issuerId={}, subjectType={}", issuerId, subjectType);
        try {
            return ResponseEntity.ok(platformMappingService.addSubjectTypeSupport(issuerId, subjectType));
        } catch (NoSuchElementException e) {
            log.error("Adding subject type support failed for issuerId: {}, subjectType: {}, error: {}",
                    issuerId, subjectType, e.getMessage());
            throw new IllegalArgumentException(e);
        }
    }
}
