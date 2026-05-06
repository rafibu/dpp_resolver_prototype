package ch.bfh.generic_dpp_platform.schemas.repositories;

import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchema;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchemaId;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

/**
 *
 * @author rbu on 21.04.2026
 */
public interface DppSchemaRepository extends JpaRepository<DppSchema, DppSchemaId> {

    default Optional<DppSchema> findNewestBySubjectType(SubjectType subjectType) {
        return findById_SubjectTypeName(subjectType.getName(), Sort.by(Sort.Direction.DESC, "majorVersion", "minorVersion"));
    }

    Optional<DppSchema> findById_SubjectTypeName(String subjectTypeName, Sort sort);
}
