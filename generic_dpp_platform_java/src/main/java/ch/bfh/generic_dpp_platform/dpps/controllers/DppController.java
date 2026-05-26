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
 * REST controller exposing platform-local DPP operations.
 * <p>
 * The read endpoints expose locally hosted DPPs and revisions. They are also used by other platforms after
 * resolver indirection: the resolver maps an issuer-qualified DPP reference to the current hosting platform,
 * and the requesting platform then fetches the revision from this controller.
 * </p>
 * <p>
 * The write endpoints implement the platform-side transition operations:
 * </p>
 * <ul>
 *     <li>{@code POST /dpps/issue} implements {@code issue}</li>
 *     <li>{@code POST /dpps/{dpp_id}/revise} implements {@code revise}</li>
 * </ul>
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

    /**
     * Returns a specific immutable revision of a locally hosted DPP.
     * <p>
     * This endpoint is the concrete platform endpoint that another platform fetches after resolving a hard
     * reference through the resolver.
     * </p>
     *
     * @param dpp_id           the issuer-qualified DPP identifier
     * @param revision_version the concrete revision version
     * @return the requested revision
     */
    @GetMapping("/{dpp_id}/{revision_version}")
    public ResponseEntity<DppRevisionResponseDTO> getDppRevision(@PathVariable String dpp_id,
                                                                 @PathVariable Integer revision_version) {
        log.info("Retrieving exact DPP revision for dpp_id: {} and revision_version: {}", dpp_id, revision_version);
        DppRevisionResponseDTO response = dppRevisionService.getDppRevision(dpp_id, revision_version);
        return ResponseEntity.ok(response);
    }

    /**
     * Issues a new logical DPP and creates its first revision.
     * <p>
     * This endpoint implements the platform-side {@code issue} operation from the transition system.
     * </p>
     *
     * @param dppRevisionDTO request containing the payload, schema version, optional DPP ID, and optional version
     * @return the created first revision
     */
    @PostMapping("/issue")
    public ResponseEntity<DppRevisionResponseDTO> issueDppRevision(@RequestBody DppRevisionRequestDTO dppRevisionDTO) {
        log.info("Creating a new DPP revision");
        DppRevisionResponseDTO createdRevision = dppRevisionService.issueDpp(dppRevisionDTO);
        return ResponseEntity.status(HttpStatus.CREATED).body(createdRevision);
    }

    /**
     * Appends a new revision to an existing logical DPP.
     * <p>
     * This endpoint implements the platform-side {@code revise} operation from the transition system.
     * </p>
     *
     * @param dpp_id         the issuer-qualified DPP identifier
     * @param dppRevisionDTO request containing the payload, schema version, and optional next version
     * @return the created revision
     */
    @PostMapping("/{dpp_id}/revise")
    public ResponseEntity<DppRevisionResponseDTO> reviseExistingDpp(@PathVariable String dpp_id,
                                                                    @RequestBody DppRevisionRequestDTO dppRevisionDTO) {
        log.info("Creating a new DPP revision for existing DPP {}", dpp_id);
        DppRevisionResponseDTO createdRevision = dppRevisionService.reviseExistingDpp(dpp_id, dppRevisionDTO);
        return ResponseEntity.status(HttpStatus.CREATED).body(createdRevision);
    }
}
