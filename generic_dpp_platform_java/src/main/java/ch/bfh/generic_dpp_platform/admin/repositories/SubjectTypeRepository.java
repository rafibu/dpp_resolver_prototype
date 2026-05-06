package ch.bfh.generic_dpp_platform.admin.repositories;

import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

/**
 *
 * @author rbu on 21.04.2026
 */
public interface SubjectTypeRepository extends JpaRepository<SubjectType, String> {
    boolean existsByName(String name);

    Optional<SubjectType> findByName(String subjectTypeName);
}
