package ch.bfh.generic_dpp_platform.schemas.controllers;

import ch.bfh.generic_dpp_platform.schemas.connectors.ResolverConnector;
import ch.bfh.generic_dpp_platform.schemas.dtos.DppSchemaDTO;
import ch.bfh.generic_dpp_platform.schemas.services.DppSchemaService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
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

    @PostMapping("/{subjectType}/sync")
    public ResponseEntity<Void> syncSchemaManually(@PathVariable String subjectType){
        log.info("Syncing schema for subject type: {}", subjectType);
        resolverConnector.syncSchema(subjectType);
        return ResponseEntity.ok().build();
    }

}
