package ch.bfh.generic_dpp_platform.admin.controllers;

import ch.bfh.generic_dpp_platform.dpps.models.ReferencedDppRevision;
import ch.bfh.generic_dpp_platform.dpps.repositories.DppRevisionRepository;
import ch.bfh.generic_dpp_platform.dpps.repositories.LogicalDppRepository;
import ch.bfh.generic_dpp_platform.dpps.repositories.ReferencedDppRevisionRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/admin")
@RequiredArgsConstructor
public class AdminController {

    private final ReferencedDppRevisionRepository cacheRepository;
    private final DppRevisionRepository revisionRepository;
    private final LogicalDppRepository logicalDppRepository;

    @GetMapping("/cache")
    public List<ReferencedDppRevision> getCache() {
        return cacheRepository.findAll();
    }

    @PostMapping("/reset")
    public void reset() {
        // Clear all data for a clean start in scenarios
        cacheRepository.deleteAll();
        revisionRepository.deleteAll();
        logicalDppRepository.deleteAll();
    }
}
