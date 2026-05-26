package ch.bfh.generic_dpp_platform.dpps.controllers;

import ch.bfh.generic_dpp_platform.dpps.dtos.DppDetailDTO;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionRequestDTO;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionResponseDTO;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppSummaryDTO;
import ch.bfh.generic_dpp_platform.dpps.services.DppRevisionService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * <p>
 * Controller for DPPs. This controller contains all read operations used by other platforms (to operationalize resolve()),
 * as well as the two write operations issue() and revise() as described in the operation system.
 * </p>
 *
 * @author rbu on 02.05.2026
 */
@Slf4j
@RestController
@RequestMapping("/dpps")
@RequiredArgsConstructor
public class DppController {

    private final DppRevisionService dppRevisionService;

    @GetMapping
    public ResponseEntity<List<DppSummaryDTO>> listDpps() {
        log.info("Listing all DPPs");
        return ResponseEntity.ok(dppRevisionService.listAllDpps());
    }

    @GetMapping("/{dpp_id}")
    public ResponseEntity<DppDetailDTO> getDppDetail(@PathVariable String dpp_id) {
        log.info("Retrieving DPP detail for dpp_id: {}", dpp_id);
        return ResponseEntity.ok(dppRevisionService.getDppDetail(dpp_id));
    }

    @GetMapping("/{dpp_id}/{revision_version}")
    public ResponseEntity<DppRevisionResponseDTO> getDppRevision(@PathVariable String dpp_id,
                                                                 @PathVariable Integer revision_version) {
        log.info("Retrieving exact DPP revision for dpp_id: {} and revision_version: {}", dpp_id, revision_version);
        DppRevisionResponseDTO response = dppRevisionService.getDppRevision(dpp_id, revision_version);
        return ResponseEntity.ok(response);
    }

    @PostMapping("/issue")
    public ResponseEntity<DppRevisionResponseDTO> createNewDppRevision(@RequestBody DppRevisionRequestDTO dppRevisionDTO) {
        log.info("Creating a new DPP revision");
        DppRevisionResponseDTO createdRevision = dppRevisionService.createNewDpp(dppRevisionDTO);
        return ResponseEntity.status(HttpStatus.CREATED).body(createdRevision);
    }

    @PostMapping("/{dpp_id}/revise")
    public ResponseEntity<DppRevisionResponseDTO> createDppRevisionForExistingDpp(@PathVariable String dpp_id,
                                                                                  @RequestBody DppRevisionRequestDTO dppRevisionDTO) {
        log.info("Creating a new DPP revision for existing DPP {}", dpp_id);
        DppRevisionResponseDTO createdRevision = dppRevisionService.createDppRevisionForExistingDpp(dpp_id, dppRevisionDTO);
        return ResponseEntity.status(HttpStatus.CREATED).body(createdRevision);
    }
}
