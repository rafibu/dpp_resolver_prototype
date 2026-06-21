package ch.bfh.generic_dpp_platform.queries.repositories;

import ch.bfh.generic_dpp_platform.queries.models.QueryAttributeFact;
import ch.bfh.generic_dpp_platform.queries.models.QueryAttributeFactId;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

/**
 * Repository for {@link QueryAttributeFact}
 *
 * @author rbu on 21.06.2026
 */
public interface QueryAttributeFactRepository extends JpaRepository<QueryAttributeFact, QueryAttributeFactId> {

    void deleteAllByIdLogicalDppId(String logicalDppId);

    List<QueryAttributeFact> findAllBySubjectTypeName(String subjectTypeName);

    List<QueryAttributeFact> findAllBySubjectTypeNameAndIdPath(String subjectTypeName, String path);
}
