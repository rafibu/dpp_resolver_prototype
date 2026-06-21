package ch.bfh.generic_dpp_platform.dpps.repositories;

import ch.bfh.generic_dpp_platform.dpps.models.DppRevision;
import ch.bfh.generic_dpp_platform.dpps.models.DppRevisionId;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

/**
 *
 * @author rbu on 02.05.2026
 */
public interface DppRevisionRepository extends JpaRepository<DppRevision, DppRevisionId> {

    default Optional<DppRevision> findCurrentByDppId(String dppId) {
        return findFirstByIdDppIdOrderByIdDppVersionDesc(dppId);
    }

    Optional<DppRevision> findFirstByIdDppIdOrderByIdDppVersionDesc(String dppId);

    List<DppRevision> findAllByIdDppIdOrderByIdDppVersionAsc(String dppId);
}
