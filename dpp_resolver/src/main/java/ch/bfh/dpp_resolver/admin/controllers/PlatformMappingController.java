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
 *
 * @author rbu on 20.04.2026
 */
@Slf4j
@RequiredArgsConstructor
@RestController
@RequestMapping("/admin/mappings")
public class PlatformMappingController {

    private final PlatformMappingService platformMappingService;

    @GetMapping
    public ResponseEntity<PlatformMappingDTO[]> getAllPlatformMappings() {
        log.info("GET all PlatformMappings");
        return ResponseEntity.ok(platformMappingService.findAll().toArray(PlatformMappingDTO[]::new));
    }

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

    @PostMapping
    public ResponseEntity<PlatformMappingDTO> createNewPlatformMapping(@RequestBody PlatformMappingDTO platformMappingDTO) {
        log.info("POST new PlatformMapping: {}", platformMappingDTO);
        try {
            return ResponseEntity.status(HttpStatus.CREATED).body(platformMappingService.save(platformMappingDTO));
        } catch (NoSuchElementException | IllegalArgumentException e) {
            log.error("PlatformMapping could not be saved", e);
            return ResponseEntity.badRequest().build();
        }
    }
}
