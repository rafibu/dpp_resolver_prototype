package ch.bfh.generic_dpp_platform.dpps.repositories;

import ch.bfh.generic_dpp_platform.dpps.models.DppRevision;
import ch.bfh.generic_dpp_platform.dpps.models.DppRevisionId;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

/**
 *
 * @author rbu on 02.05.2026
 */
public interface DppRevisionRepository extends JpaRepository<DppRevision, DppRevisionId> {

    /**
     * Finds the latest revision for a given DPP ID, ordered by version descending.
     *
     * @param dppId the DPP identifier
     * @return an Optional containing the latest revision, if any
     */
    Optional<DppRevision> findFirstByIdDppIdOrderByIdDppVersionDesc(String dppId);
}
