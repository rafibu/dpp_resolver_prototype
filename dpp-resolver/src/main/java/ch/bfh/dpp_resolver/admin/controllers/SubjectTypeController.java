package ch.bfh.dpp_resolver.admin.controllers;

import ch.bfh.dpp_resolver.admin.dto.SubjectTypeDTO;
import ch.bfh.dpp_resolver.admin.services.SubjectTypeService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 *
 * @author rbu on 17.04.2026
 */
@Slf4j
@RequiredArgsConstructor
@RestController
@RequestMapping("/admin/subject-types")
public class SubjectTypeController {

    private final SubjectTypeService subjectTypeService;

    @GetMapping
    public ResponseEntity<SubjectTypeDTO[]> getSubjectTypes() {
        log.info("GET All SubjectTypes");
        return ResponseEntity.ok(subjectTypeService.findAll());
    }

    @PostMapping
    public ResponseEntity<SubjectTypeDTO> postSubjectType(@RequestBody SubjectTypeDTO subjectTypeDTO) {
        log.info("POST SubjectType: {}", subjectTypeDTO);
        if (subjectTypeDTO.getName() == null) {
            return ResponseEntity.badRequest().build();
        }
        subjectTypeService.save(subjectTypeDTO);
        return ResponseEntity.status(HttpStatus.CREATED).body(subjectTypeDTO);
    }
}
