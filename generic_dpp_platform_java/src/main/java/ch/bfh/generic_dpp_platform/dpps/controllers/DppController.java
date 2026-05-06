package ch.bfh.generic_dpp_platform.dpps.controllers;

import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionRequestDTO;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionResponseDTO;
import ch.bfh.generic_dpp_platform.dpps.exceptions.DppAlreadyExistsException;
import ch.bfh.generic_dpp_platform.dpps.exceptions.DppRevisionConflictException;
import ch.bfh.generic_dpp_platform.dpps.services.DppRevisionService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.NoSuchElementException;

/**
 *
 * @author rbu on 02.05.2026
 */
@Slf4j
@RestController
@RequestMapping("/dpps")
@RequiredArgsConstructor
public class DppController {

    private final DppRevisionService dppRevisionService;

    @GetMapping("/{dpp_id}")
    public ResponseEntity<DppRevisionResponseDTO> getCurrentDppRevision(@PathVariable String dpp_id) {
        log.info("Retrieving current DPP revision for dpp_id: {}", dpp_id);
        DppRevisionResponseDTO response = dppRevisionService.getCurrentDppRevision(dpp_id);
        return ResponseEntity.ok(response);
    }

    @GetMapping("/{dpp_id}/{revision_version}")
    public ResponseEntity<DppRevisionResponseDTO> getDppRevision(@PathVariable String dpp_id,
                                                                 @PathVariable Integer revision_version) {
        log.info("Retrieving exact DPP revision for dpp_id: {} and revision_version: {}", dpp_id, revision_version);
        DppRevisionResponseDTO response = dppRevisionService.getDppRevision(dpp_id, revision_version);
        return ResponseEntity.ok(response);
    }

    @PostMapping
    public ResponseEntity<DppRevisionResponseDTO> createNewDppRevision(@RequestBody DppRevisionRequestDTO dppRevisionDTO) {
        log.info("Creating a new DPP revision");
        DppRevisionResponseDTO createdRevision = dppRevisionService.createNewDpp(dppRevisionDTO);
        return ResponseEntity.status(HttpStatus.CREATED).body(createdRevision);
    }

    @PostMapping("/{dpp_id}")
    public ResponseEntity<DppRevisionResponseDTO> createDppRevisionForExistingDpp(@PathVariable String dpp_id,
                                                                                  @RequestBody DppRevisionRequestDTO dppRevisionDTO) {
        log.info("Creating a new DPP revision for existing DPP {}", dpp_id);
        DppRevisionResponseDTO createdRevision = dppRevisionService.createDppRevisionForExistingDpp(dpp_id, dppRevisionDTO);
        return ResponseEntity.status(HttpStatus.CREATED).body(createdRevision);
    }


}
