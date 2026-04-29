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
 *
 * @author rbu on 20.04.2026
 */
@Slf4j
@RequiredArgsConstructor
@RestController
@RequestMapping("/schemas")
public class DppSchemaController {

    private final DppSchemaService schemaService;

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

    @GetMapping("/{subjectType}/{majorVersion}/{minorVersion}")
    public ResponseEntity<DppSchemaDTO> getDppSchema(@PathVariable String subjectType, @PathVariable int majorVersion, @PathVariable int minorVersion) {
        log.info("GET DPP Schema for SubjectType: {}, MajorVersion: {}, MinorVersion: {}", subjectType, majorVersion, minorVersion);
        try {
            return ResponseEntity.ok(schemaService.findExactSchema(subjectType, majorVersion, minorVersion));
        } catch (NoSuchElementException e) {
            log.error("Schema for SubjectType {}, version {}.{} not found", subjectType, majorVersion, minorVersion);
            return ResponseEntity.notFound().build();
        }
    }

    @PostMapping
    public ResponseEntity<DppSchemaDTO> createNewDppSchema(@RequestBody DppSchemaDTO dppSchemaDTO) {
        log.info("POST new DPP Schema: {}", dppSchemaDTO);
        try {
            return ResponseEntity.status(HttpStatus.CREATED).body(schemaService.save(dppSchemaDTO));
        } catch (NoSuchElementException | IllegalArgumentException e) {
            log.error("DPP Schema could not be saved", e);
            return ResponseEntity.badRequest().build();
        }
    }

}
