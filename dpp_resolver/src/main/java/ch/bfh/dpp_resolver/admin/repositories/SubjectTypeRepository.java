package ch.bfh.dpp_resolver.admin.repositories;

import ch.bfh.dpp_resolver.admin.models.SubjectType;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;


/**
 *
 * @author rbu on 17.04.2026
 */
public interface SubjectTypeRepository extends JpaRepository<SubjectType, Long>{
    boolean existsByName(String name);

    Optional<SubjectType> findByName(String subjectType);
}
