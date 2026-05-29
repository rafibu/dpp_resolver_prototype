package ch.bfh.dpp_resolver.admin.repositories;

import ch.bfh.dpp_resolver.admin.models.Platform;
import ch.bfh.dpp_resolver.admin.models.SubjectType;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

/**
 *
 * @author rbu on 20.04.2026
 */
public interface PlatformRepository extends JpaRepository<Platform, Long> {
    Optional<Platform> findByAbbreviation(String abbreviation);
}
