package ch.bfh.generic_dpp_platform.admin.controllers;

import ch.bfh.generic_dpp_platform.admin.services.AdminService;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionResponseDTO;
import ch.bfh.generic_dpp_platform.dpps.models.ReferencedDppRevision;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/admin")
@RequiredArgsConstructor
public class AdminController {

    private final AdminService adminService;

    @GetMapping("/cache")
    public List<ReferencedDppRevision> getCache() {
        return adminService.getCache();
    }

    @PostMapping("/reset")
    public void reset() {
        adminService.resetPlatformData();
    }

    /**
     * Import already-issued immutable revisions into this platform.
     * <p>
     * Scenario S1 uses this endpoint to model issuer migration: the old hosting platform copies concrete
     * revisions to a successor platform, then the resolver route is moved. The controller intentionally delegates
     * all checks to {@link AdminService}; the endpoint is an administrative orchestration helper, not a second
     * DPP lifecycle implementation.
     * </p>
     *
     * @param revisions copied revision DTOs, including their original payload hashes
     * @return the stored revisions after validation and idempotent import
     */
    @PostMapping("/import-revisions")
    public List<DppRevisionResponseDTO> importRevisions(@RequestBody List<DppRevisionResponseDTO> revisions) {
        return adminService.importRevisions(revisions);
    }
}
