package ch.bfh.generic_dpp_platform.queries.repositories;

import ch.bfh.generic_dpp_platform.queries.dtos.PredicateFilterDTO;
import ch.bfh.generic_dpp_platform.queries.models.QueryAttributeFact;
import ch.bfh.generic_dpp_platform.queries.models.QueryAttributeFactId;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.math.BigDecimal;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;


/**
 * Repository for {@link QueryAttributeFact}
 *
 * @author rbu on 21.06.2026
 */
public interface QueryAttributeFactRepository extends JpaRepository<QueryAttributeFact, QueryAttributeFactId> {

    void deleteAllByIdLogicalDppId(String logicalDppId);

    List<QueryAttributeFact> findAllBySubjectTypeName(String subjectTypeName);

    /**
     * Selects indexed attribute facts for logical DPPs of the given subject type that satisfy all supplied filters.
     * <p>
     * Filtering is performed in two stages:
     * first, each {@link PredicateFilterDTO} is evaluated through repository queries that return matching logical DPP IDs;
     * then those ID sets are intersected so that only logical DPPs satisfying every filter remain.
     * The returned facts are loaded only for the matching logical DPP IDs.
     * </p>
     * <p>
     * If {@code returnFields} is {@code null} or empty, all indexed facts for each matching logical DPP are returned.
     * Otherwise, only facts whose path is contained in {@code returnFields} are returned.
     * This method returns flat {@link QueryAttributeFact} rows; callers remain responsible for grouping them by logical
     * DPP ID and shaping the final query result.
     * </p>
     * <p>
     *     NOTE: For even better filtering performance the full filter should be applied in a single query.
     *     For this we would need to use JDBC or similar.
     * </p>
     *
     * @param subjectTypes the subject type whose indexed facts should be queried
     * @param filters         the AND-connected predicate filters to apply; {@code null} or empty means no filtering
     * @param returnFields    optional fact paths to project; {@code null} or empty means all paths
     * @return indexed facts for matching logical DPPs, optionally restricted to the requested return fields
     */
    default List<QueryAttributeFact> findAllBySubjectTypesNameAndFilters(
            List<String> subjectTypes,
            List<PredicateFilterDTO> filters,
            List<String> returnFields
    ) {
        Set<String> matchingLogicalDppIds = matchingLogicalDppIds(subjectTypes, filters);

        if (matchingLogicalDppIds.isEmpty()) {
            return List.of();
        }

        if (returnFields == null || returnFields.isEmpty()) {
            return findAllBySubjectTypeNameInAndIdLogicalDppIdIn(subjectTypes, matchingLogicalDppIds);
        }

        return findAllBySubjectTypeNameInAndIdLogicalDppIdInAndIdPathIn(
                subjectTypes,
                matchingLogicalDppIds,
                returnFields
        );
    }

    default Set<String> matchingLogicalDppIds(List<String> subjectTypes, List<PredicateFilterDTO> filters) {
        if (filters == null || filters.isEmpty()) {
            return new LinkedHashSet<>(findDistinctLogicalDppIdsBySubjectTypeName(subjectTypes));
        }

        Set<String> result = null;

        for (PredicateFilterDTO filter : filters) {
            Set<String> filterMatches = new LinkedHashSet<>(matchingLogicalDppIds(subjectTypes, filter));

            if (result == null) {
                result = filterMatches;
            } else {
                result.retainAll(filterMatches);
            }

            if (result.isEmpty()) {
                return Set.of();
            }
        }

        return result;
    }

    default List<String> matchingLogicalDppIds(List<String> subjectTypes, PredicateFilterDTO filter) {
        return switch (filter.getOperator()) {
            case EQ -> findLogicalDppIdsByEqualValue(subjectTypes, filter.getPath(), filter.getValue());
            case NEQ -> findLogicalDppIdsByNotEqualValue(subjectTypes, filter.getPath(), filter.getValue());
            case EXISTS -> findLogicalDppIdsByExistingPath(subjectTypes, filter.getPath());
            case NOT_EXISTS -> findLogicalDppIdsByMissingPath(subjectTypes, filter.getPath());
            case IN -> findLogicalDppIdsByValueIn(subjectTypes, filter.getPath(), filterValues(filter.getValue()));
            case GT ->
                    findLogicalDppIdsByNumberGreaterThan(subjectTypes, filter.getPath(), numberValue(filter.getValue()));
            case GTE ->
                    findLogicalDppIdsByNumberGreaterThanOrEqual(subjectTypes, filter.getPath(), numberValue(filter.getValue()));
            case LT ->
                    findLogicalDppIdsByNumberLessThan(subjectTypes, filter.getPath(), numberValue(filter.getValue()));
            case LTE ->
                    findLogicalDppIdsByNumberLessThanOrEqual(subjectTypes, filter.getPath(), numberValue(filter.getValue()));
        };
    }

    default List<String> findLogicalDppIdsByEqualValue(List<String> subjectTypes, String path, Object value) {
        if (value instanceof Number) {
            return findLogicalDppIdsByNumberEqual(subjectTypes, path, numberValue(value));
        }
        if (value instanceof Boolean booleanValue) {
            return findLogicalDppIdsByBooleanEqual(subjectTypes, path, booleanValue);
        }
        //Since the Request mapper doesn't map strings to boolean values, we need to check for "true" and "false" strings
        String stringValue = String.valueOf(value);
        if ("true".equalsIgnoreCase(stringValue) || "false".equalsIgnoreCase(stringValue)) {
            return findLogicalDppIdsByBooleanEqual(subjectTypes, path, Boolean.parseBoolean(stringValue));
        }
        return findLogicalDppIdsByTextEqual(subjectTypes, path, stringValue);
    }

    default List<String> findLogicalDppIdsByValueIn(List<String> subjectTypes, String path, Collection<?> values) {
        if (values == null || values.isEmpty()) {
            return List.of();
        }

        Object firstValue = values.iterator().next();
        if (firstValue instanceof Boolean) {
            return findLogicalDppIdsByBooleanIn(
                    subjectTypes,
                    path,
                    values.stream().map(Boolean.class::cast).toList()
            );
        }
        if (firstValue instanceof Number) {
            return findLogicalDppIdsByNumberIn(
                    subjectTypes,
                    path,
                    values.stream().map(QueryAttributeFactRepository::numberValue).toList()
            );
        }
        return findLogicalDppIdsByTextIn(
                subjectTypes,
                path,
                values.stream().map(String::valueOf).toList()
        );
    }

    private static BigDecimal numberValue(Object value) {
        if (value instanceof BigDecimal bigDecimal) {
            return bigDecimal;
        }

        if (value instanceof Number number) {
            return new BigDecimal(number.toString());
        }
        return new BigDecimal(String.valueOf(value));
    }

    private static Collection<?> filterValues(Object value) {
        if (value instanceof Collection<?> collection) {
            return collection;
        }
        if (value instanceof Object[] array) {
            return List.of(array);
        }
        return List.of();
    }

    List<QueryAttributeFact> findAllBySubjectTypeNameInAndIdLogicalDppIdIn(
            List<String> subjectTypeNames,
            Collection<String> logicalDppIds
    );

    List<QueryAttributeFact> findAllBySubjectTypeNameInAndIdLogicalDppIdInAndIdPathIn(
            List<String> subjectTypeNames,
            Collection<String> logicalDppIds,
            Collection<String> paths
    );

    @Query("""
            select distinct fact.id.logicalDppId
            from QueryAttributeFact fact
            where fact.subjectType.name in :subjectTypes
            """)
    List<String> findDistinctLogicalDppIdsBySubjectTypeName(List<String> subjectTypes);


    @Query("""
            select distinct fact.id.logicalDppId
            from QueryAttributeFact fact
            where fact.subjectType.name in :subjectTypes
              and fact.id.path = :path
              and fact.valueText = :value
            """)
    List<String> findLogicalDppIdsByTextEqual(List<String> subjectTypes, String path, String value);

    @Query("""
            select distinct fact.id.logicalDppId
            from QueryAttributeFact fact
            where fact.subjectType.name in :subjectTypes
              and fact.id.path = :path
              and fact.valueNumber = :value
            """)
    List<String> findLogicalDppIdsByNumberEqual(List<String> subjectTypes, String path, BigDecimal value);

    @Query("""
            select distinct fact.id.logicalDppId
            from QueryAttributeFact fact
            where fact.subjectType.name in :subjectTypes
              and fact.id.path = :path
              and fact.valueBoolean = :value
            """)
    List<String> findLogicalDppIdsByBooleanEqual(List<String> subjectTypes, String path, Boolean value);


    default List<String> findLogicalDppIdsByNotEqualValue(List<String> subjectTypes, String path, Object value) {
        if (value instanceof Boolean booleanValue) {
            return findLogicalDppIdsByBooleanNotEqual(subjectTypes, path, booleanValue);
        }
        if (value instanceof Number) {
            return findLogicalDppIdsByNumberNotEqual(subjectTypes, path, numberValue(value));
        }
        return findLogicalDppIdsByTextNotEqual(subjectTypes, path, String.valueOf(value));
    }

    @Query("""
            select distinct fact.id.logicalDppId
            from QueryAttributeFact fact
            where fact.subjectType.name in :subjectTypes
              and fact.id.path = :path
              and fact.valueText is not null
              and fact.valueText <> :value
            """)
    List<String> findLogicalDppIdsByTextNotEqual(List<String> subjectTypes, String path, String value);

    @Query("""
            select distinct fact.id.logicalDppId
            from QueryAttributeFact fact
            where fact.subjectType.name in :subjectTypes
              and fact.id.path = :path
              and fact.valueNumber is not null
              and fact.valueNumber <> :value
            """)
    List<String> findLogicalDppIdsByNumberNotEqual(List<String> subjectTypes, String path, BigDecimal value);

    @Query("""
            select distinct fact.id.logicalDppId
            from QueryAttributeFact fact
            where fact.subjectType.name in :subjectTypes
              and fact.id.path = :path
              and fact.valueBoolean is not null
              and fact.valueBoolean <> :value
            """)
    List<String> findLogicalDppIdsByBooleanNotEqual(List<String> subjectTypes, String path, Boolean value);

    @Query("""
            select distinct fact.id.logicalDppId
            from QueryAttributeFact fact
            where fact.subjectType.name in :subjectTypes
              and fact.id.path = :path
              and (
                    fact.valueText is not null
                 or fact.valueNumber is not null
                 or fact.valueBoolean is not null
              )
            """)
    List<String> findLogicalDppIdsByExistingPath(List<String> subjectTypes, String path);

    @Query("""
            select distinct candidate.id.logicalDppId
            from QueryAttributeFact candidate
            where candidate.subjectType.name in :subjectTypes
              and not exists (
                    select 1
                    from QueryAttributeFact fact
                    where fact.subjectType.name in :subjectTypes
                      and fact.id.logicalDppId = candidate.id.logicalDppId
                      and fact.id.path = :path
                      and (
                            fact.valueText is not null
                         or fact.valueNumber is not null
                         or fact.valueBoolean is not null
                      )
              )
            """)
    List<String> findLogicalDppIdsByMissingPath(List<String> subjectTypes, String path);

    @Query("""
            select distinct fact.id.logicalDppId
            from QueryAttributeFact fact
            where fact.subjectType.name in :subjectTypes
              and fact.id.path = :path
              and fact.valueText in :values
            """)
    List<String> findLogicalDppIdsByTextIn(List<String> subjectTypes, String path, Collection<String> values);

    @Query("""
            select distinct fact.id.logicalDppId
            from QueryAttributeFact fact
            where fact.subjectType.name in :subjectTypes
              and fact.id.path = :path
              and fact.valueNumber in :values
            """)
    List<String> findLogicalDppIdsByNumberIn(List<String> subjectTypes, String path, Collection<BigDecimal> values);

    @Query("""
            select distinct fact.id.logicalDppId
            from QueryAttributeFact fact
            where fact.subjectType.name in :subjectTypes
              and fact.id.path = :path
              and fact.valueBoolean in :values
            """)
    List<String> findLogicalDppIdsByBooleanIn(List<String> subjectTypes, String path, Collection<Boolean> values);

    @Query("""
            select distinct fact.id.logicalDppId
            from QueryAttributeFact fact
            where fact.subjectType.name in :subjectTypes
              and fact.id.path = :path
              and fact.valueNumber > :value
            """)
    List<String> findLogicalDppIdsByNumberGreaterThan(List<String> subjectTypes, String path, BigDecimal value);

    @Query("""
            select distinct fact.id.logicalDppId
            from QueryAttributeFact fact
            where fact.subjectType.name in :subjectTypes
              and fact.id.path = :path
              and fact.valueNumber >= :value
            """)
    List<String> findLogicalDppIdsByNumberGreaterThanOrEqual(List<String> subjectTypes, String path, BigDecimal value);

    @Query("""
            select distinct fact.id.logicalDppId
            from QueryAttributeFact fact
            where fact.subjectType.name in :subjectTypes
              and fact.id.path = :path
              and fact.valueNumber < :value
            """)
    List<String> findLogicalDppIdsByNumberLessThan(List<String> subjectTypes, String path, BigDecimal value);

    @Query("""
            select distinct fact.id.logicalDppId
            from QueryAttributeFact fact
            where fact.subjectType.name in :subjectTypes
              and fact.id.path = :path
              and fact.valueNumber <= :value
            """)
    List<String> findLogicalDppIdsByNumberLessThanOrEqual(List<String> subjectTypes, String path, BigDecimal value);

}