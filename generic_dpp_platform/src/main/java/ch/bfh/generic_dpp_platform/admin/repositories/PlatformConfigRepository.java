package ch.bfh.generic_dpp_platform.admin.repositories;

import ch.bfh.generic_dpp_platform.admin.models.PlatformConfigEntry;
import org.springframework.data.jpa.repository.JpaRepository;

/**
 *
 * @author rbu on 21.04.2026
 */
public interface PlatformConfigRepository extends JpaRepository<PlatformConfigEntry, String> {
}
