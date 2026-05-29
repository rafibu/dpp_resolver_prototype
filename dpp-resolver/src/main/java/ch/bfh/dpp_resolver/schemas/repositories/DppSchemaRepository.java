package ch.bfh.dpp_resolver.schemas.repositories;

import ch.bfh.dpp_resolver.schemas.models.DppSchema;
import ch.bfh.dpp_resolver.schemas.models.DppSchemaId;
import ch.bfh.dpp_resolver.admin.models.SubjectType;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

/**
 *
 * @author rbu on 20.04.2026
 */
public interface DppSchemaRepository extends JpaRepository<DppSchema, DppSchemaId> {
    default DppSchema findActiveBySubjectType(SubjectType subjectType) {
        //We assume that the newest schema has the latest version number for simplicity
        Sort sort = Sort.by(Sort.Direction.DESC, "publishedAt");
        return findFirstBySubjectType(subjectType, sort);
    }

    DppSchema findFirstBySubjectType(SubjectType subjectType, Sort sort);

    default Optional<DppSchema> findExactSchema(SubjectType subjectType, int majorVersion, int minorVersion) {
        return findBySubjectTypeAndId_MajorVersionAndId_MinorVersion(subjectType, majorVersion, minorVersion);
    }

    Optional<DppSchema> findBySubjectTypeAndId_MajorVersionAndId_MinorVersion(SubjectType subjectType, int majorVersion, int minorVersion);

    List<DppSchema> findAllBySubjectType(SubjectType subjectType);
}
