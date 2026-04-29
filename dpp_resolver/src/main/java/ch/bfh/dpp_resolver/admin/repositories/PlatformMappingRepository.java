package ch.bfh.dpp_resolver.admin.repositories;

import ch.bfh.dpp_resolver.admin.dto.PlatformMappingDTO;
import ch.bfh.dpp_resolver.admin.models.PlatformMapping;
import ch.bfh.dpp_resolver.admin.models.SubjectType;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

/**
 *
 * @author rbu on 20.04.2026
 */
public interface PlatformMappingRepository extends JpaRepository<PlatformMapping, Long> {
    List<PlatformMapping> findAllBySubjectType(SubjectType subjectType);

    Optional<PlatformMapping> findBySubjectTypeAndAbbreviation(SubjectType subjectType, String abbreviation);
}
