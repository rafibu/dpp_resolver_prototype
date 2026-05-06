package ch.bfh.generic_dpp_platform.dpps.repositories;

import ch.bfh.generic_dpp_platform.dpps.models.LogicalDpp;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;

import java.util.Optional;

/**
 *
 * @author rbu on 02.05.2026
 */
public interface LogicalDppRepository extends JpaRepository<LogicalDpp, String> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    Optional<LogicalDpp> findWithLockByDppId(String dppId);
}
