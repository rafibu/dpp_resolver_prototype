package ch.bfh.dpp_resolver.schemas.controllers;

import ch.bfh.dpp_resolver.schemas.dtos.DppSchemaDTO;
import ch.bfh.dpp_resolver.schemas.services.DppSchemaService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.NoSuchElementException;

/**
 * HTTP controller for the authoritative schema set that forms part of the resolver
 * state (Definition 6).
 *
 * <p>Exposes the {@code publishSchema} operation and read access to
 * schema artefacts (Definition 3) for DPP platforms executing the {@code cacheSchema}
 * operation.</p>
 *
 * <p>Schema publication is the only write operation. Published schemas are immutable:
 * once added to the authoritative set they are never removed, ensuring
 * that historical revisions remain interpretable (Invariant I3 combined with Invariant I5).</p>
 */
@Slf4j
@RequiredArgsConstructor
@RestController
@RequestMapping("/schemas")
public class DppSchemaController {

    private final DppSchemaService schemaService;

    /**
     * Returns all schema artefacts published for a given subject type.
     *
     * <p>Used by DPP platforms during the {@code cacheSchema} operation
     * to fetch all published versions of a subject type's schema into their local cache.</p>
     *
     * @param subjectType the subject type name
     * @return all published schemas for the subject type, or 404 if the subject type is unknown
     */
    @GetMapping("/{subjectType}")
    public ResponseEntity<DppSchemaDTO[]> getAllDppSchemasForSubjectType(@PathVariable String subjectType) {
        log.info("GET all DPP Schema for SubjectType: {}", subjectType);
        try {
            return ResponseEntity.ok(schemaService.findAllBySubjectType(subjectType).toArray(DppSchemaDTO[]::new));
        } catch (NoSuchElementException e) {
            log.error("Active Schema for SubjectType {} not found", subjectType);
            return ResponseEntity.notFound().build();
        }
    }

    /**
     * Returns the most recently published schema artefact for a given subject type.
     *
     * <p>The active schema is the schema with the highest (major, minor) version.
     * DPP platforms use this endpoint to discover the current schema for a subject type
     * before issuing new revisions.</p>
     *
     * @param subjectType the subject type name
     * @return the active schema artefact, or 404 if none exists
     */
    @GetMapping("/{subjectType}/current")
    public ResponseEntity<DppSchemaDTO> getActiveDppSchema(@PathVariable String subjectType) {
        log.info("GET newest DPP Schema for SubjectType: {}", subjectType);
        try {
            return ResponseEntity.ok(schemaService.findActiveBySubjectType(subjectType));
        } catch (NoSuchElementException e) {
            log.error("Active Schema for SubjectType {} not found", subjectType);
            return ResponseEntity.notFound().build();
        }
    }

    /**
     * Returns the exact schema artefact for a given subject type and (major, minor) version.
     *
     * <p>DPP platforms use this endpoint during the {@code cacheSchema} operation to fetch
     * a specific schema version referenced in an incoming revision (Invariant I3).</p>
     *
     * @param subjectType  the subject type name
     * @param majorVersion the major version component (Definition 3)
     * @param minorVersion the minor version component (Definition 3)
     * @return the exact schema artefact, or 404 if not found
     */
    @GetMapping("/{subjectType}/{majorVersion}/{minorVersion}")
    public ResponseEntity<DppSchemaDTO> getDppSchema(
            @PathVariable String subjectType,
            @PathVariable int majorVersion,
            @PathVariable int minorVersion) {
        log.info("GET DPP Schema for SubjectType: {}, MajorVersion: {}, MinorVersion: {}", subjectType, majorVersion, minorVersion);
        try {
            return ResponseEntity.ok(schemaService.findExactSchema(subjectType, majorVersion, minorVersion));
        } catch (NoSuchElementException e) {
            log.error("Schema for SubjectType {}, version {}.{} not found", subjectType, majorVersion, minorVersion);
            return ResponseEntity.notFound().build();
        }
    }

    /**
     * Publishes a new schema artefact to the authoritative schema set, implementing the
     * {@code publishSchema} operation.
     *
     * <p>Enforces version monotonicity, backward compatibility for minor updates
     * (Definitions 15 and 16), and schema-graph acyclicity (Invariant I6). Returns 422
     * if publication would introduce a cycle or self-reference into the schema dependency
     * graph (Definition 13).</p>
     *
     * @param dppSchemaDTO the schema artefact to publish, including subject type, version, and JSON Schema document
     * @return the published schema artefact with HTTP 201, or 400 on validation failure
     */
    @PostMapping
    public ResponseEntity<DppSchemaDTO> publishSchema(@RequestBody DppSchemaDTO dppSchemaDTO) {
        log.info("POST new DPP Schema: {}", dppSchemaDTO);
        try {
            return ResponseEntity.status(HttpStatus.CREATED).body(schemaService.save(dppSchemaDTO));
        } catch (NoSuchElementException | IllegalArgumentException e) {
            log.error("DPP Schema could not be saved", e);
            return ResponseEntity.badRequest().build();
        }
    }

}
