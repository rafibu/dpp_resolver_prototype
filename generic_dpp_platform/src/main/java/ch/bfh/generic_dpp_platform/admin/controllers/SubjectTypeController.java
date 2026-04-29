package ch.bfh.generic_dpp_platform.admin.controllers;

import ch.bfh.generic_dpp_platform.admin.dtos.SubjectTypeDTO;
import ch.bfh.generic_dpp_platform.admin.services.SubjectTypeService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 *
 * @author rbu on 21.04.2026
 */
@Slf4j
@RestController
@RequestMapping("/admin/subject-types")
@RequiredArgsConstructor
public class SubjectTypeController {

    private final SubjectTypeService subjectTypeService;

    @GetMapping
    public ResponseEntity<SubjectTypeDTO[]> getAllSupportedSubjectTypes() {
        log.info("Retrieving all supported subject types");
        return ResponseEntity.ok(subjectTypeService.getAllSupportedSubjectTypes().toArray(SubjectTypeDTO[]::new));
    }

    @PostMapping
    public ResponseEntity<SubjectTypeDTO> createSubjectType(@RequestBody SubjectTypeDTO subjectTypeDTO) {
        log.info("Creating a new subject type");
        SubjectTypeDTO createdSubjectType = subjectTypeService.createSubjectType(subjectTypeDTO);
        return ResponseEntity.status(HttpStatus.CREATED).body(createdSubjectType);
    }
}
