package ch.bfh.generic_dpp_platform.dpps.repositories;

import ch.bfh.generic_dpp_platform.dpps.models.ReferencedDppRevision;
import ch.bfh.generic_dpp_platform.dpps.models.ReferencedDppRevisionId;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.time.Instant;

@Repository
public interface ReferencedDppRevisionRepository extends JpaRepository<ReferencedDppRevision, ReferencedDppRevisionId> {
    void deleteByFetchedAtBefore(Instant expiryDate);
}
