package ch.bfh.generic_dpp_platform.schemas.controllers;

import ch.bfh.generic_dpp_platform.schemas.connectors.ResolverConnector;
import ch.bfh.generic_dpp_platform.schemas.dtos.DppSchemaDTO;
import ch.bfh.generic_dpp_platform.schemas.services.DppSchemaService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * REST controller for platform-local schema cache access.
 * <p>
 * This controller does not publish schemas and does not mutate the resolver's authoritative schema set.
 * It exposes schemas that this DPP platform has already cached from the resolver and provides a manual trigger
 * for the platform-side {@code cacheSchema} operation.
 * </p>
 * <p>
 * Resolver-side operations such as schema publication, compatibility checking, and schema-dependency graph
 * acyclicity are intentionally outside this controller.
 * </p>
 *
 * @author rbu on 21.04.2026
 */
@Slf4j
@RestController
@RequestMapping("/schemas")
@RequiredArgsConstructor
public class DppSchemaController {

    private final DppSchemaService dppSchemaService;
    private final ResolverConnector resolverConnector;

    @GetMapping("/{subjectType}")
    public ResponseEntity<DppSchemaDTO> getCurrentSchemaBySubjectType(@PathVariable String subjectType){
        log.info("Retrieving current schema for subject type: {}", subjectType);
        return ResponseEntity.ok(dppSchemaService.getCurrentSchema(subjectType));
    }

    @GetMapping("/{subjectType}/{major}/{minor}")
    public ResponseEntity<DppSchemaDTO> getExactSchemaBySubjectType(@PathVariable String subjectType, @PathVariable int major, @PathVariable int minor){
        log.info("Retrieving exact schema for subject type: {}, major: {}, minor: {}", subjectType, major, minor);
        return ResponseEntity.ok(dppSchemaService.getExactSchema(subjectType, major, minor));
    }

    /**
     * Manually fetches schemas for a subject type from the resolver into the local platform cache.
     * <p>
     * This endpoint implements the platform-side {@code cacheSchema} operation. It does not create schemas;
     * it only copies resolver-published schemas into this platform's cache.
     * </p>
     *
     * @param subjectType the subject type whose schemas should be cached from the resolver
     * @return an empty response when the cache operation has completed
     */
    @PostMapping("/{subjectType}/cacheSchema")
    public ResponseEntity<Void> cacheSchemaManually(@PathVariable String subjectType){
        log.info("Caching new schemas for subject type: {}", subjectType);
        resolverConnector.cacheSchema(subjectType);
        return ResponseEntity.ok().build();
    }

}
