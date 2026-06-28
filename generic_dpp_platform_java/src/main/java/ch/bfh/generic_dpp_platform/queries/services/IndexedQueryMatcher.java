package ch.bfh.generic_dpp_platform.queries.services;

import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import ch.bfh.generic_dpp_platform.admin.services.PlatformConfigService;
import ch.bfh.generic_dpp_platform.queries.dtos.PredicateQueryRequestDTO;
import ch.bfh.generic_dpp_platform.queries.dtos.TraverseQueryRequestDTO;
import ch.bfh.generic_dpp_platform.queries.dtos.TraverseSourceScopeDTO;
import ch.bfh.generic_dpp_platform.queries.models.QueryAttributeFact;
import ch.bfh.generic_dpp_platform.queries.repositories.QueryAttributeFactRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.*;
import java.util.stream.Stream;

/**
 * Evaluates local derived queries from materialized attribute facts.
 *
 * <p>The facts are the platform's indexed representation of the derived query
 * view for current revisions. Indexing moves projection work to issue and
 * revise; it is an execution optimization and must preserve the on-demand
 * result semantics.</p>
 */
@Service
public class IndexedQueryMatcher extends AbstractQueryMatcher {

    private final QueryAttributeFactRepository queryAttributeFactRepository;

    public IndexedQueryMatcher(PlatformConfigService platformConfigService,
                               SubjectTypeRepository subjectTypeRepository,
                               QueryAttributeFactRepository queryAttributeFactRepository) {
        super(platformConfigService, subjectTypeRepository);
        this.queryAttributeFactRepository = queryAttributeFactRepository;
    }

    /**
     * Selects projected attribute facts for local groups that satisfy all filters.
     */
    @Override
    @Transactional(readOnly = true)
    protected Object queryMatches(PredicateQueryRequestDTO request) {
        return matchingSelectedFactValues(request).toList();
    }

    /**
     * Counts local attribute-fact groups that satisfy all filters.
     */
    @Override
    @Transactional(readOnly = true)
    protected Long queryCount(PredicateQueryRequestDTO request) {
        return matchingFactGroups(request).count();
    }

    /**
     * Sums the requested numeric attribute fact over matching local groups.
     */
    @Override
    @Transactional(readOnly = true)
    protected Double querySum(PredicateQueryRequestDTO request) {
        return matchingFactGroups(request)
                .map(factsByPath -> factsByPath.get(request.getAggregatePath()))
                .filter(Objects::nonNull)
                .map(this::requireNumericFact)
                .mapToDouble(BigDecimal::doubleValue)
                .sum();
    }

    /**
     * Performs reverse traversal by testing indexed reference facts in each source scope.
     */
    @Override
    @Transactional(readOnly = true)
    protected List<Object> executeTraverseQuery(TraverseQueryRequestDTO request) {
        List<Object> matches = new LinkedList<>();

        for (TraverseSourceScopeDTO sourceScope : request.getSources()) {
            List<Object> scopeMatches = factsGroupedByDpp(sourceScope.getSubjectType())
                    .values()
                    .stream()
                    .filter(factsByPath -> indexedFactsContainReference(factsByPath, sourceScope, request))
                    .map(factsByPath -> (Object) factValuesByPath(factsByPath))
                    .toList();
            matches.addAll(scopeMatches);
        }

        return matches;
    }

    private boolean indexedFactsContainReference(
            Map<String, QueryAttributeFact> factsByPath,
            TraverseSourceScopeDTO sourceScope,
            TraverseQueryRequestDTO request
    ) {
        if (sourceScope.getReferencePaths() == null || sourceScope.getReferencePaths().isEmpty()) {
            return factsByPath.entrySet()
                    .stream()
                    .filter(entry -> isReferenceFactPath(entry.getKey()))
                    .anyMatch(entry -> indexedReferenceMatches(factsByPath, entry.getKey(), entry.getValue(), request));
        }

        return sourceScope.getReferencePaths()
                .stream()
                .anyMatch(referencePath -> indexedReferencePathMatches(factsByPath, referencePath, request));
    }

    private boolean indexedReferencePathMatches(
            Map<String, QueryAttributeFact> factsByPath,
            String referencePath,
            TraverseQueryRequestDTO request
    ) {
        QueryAttributeFact directReferenceFact = factsByPath.get(referencePath);
        if (directReferenceFact != null && indexedReferenceMatches(factsByPath, referencePath, directReferenceFact, request)) {
            return true;
        }

        String refPath = referencePath + ".$ref";
        QueryAttributeFact nestedReferenceFact = factsByPath.get(refPath);
        return nestedReferenceFact != null && indexedReferenceMatches(factsByPath, refPath, nestedReferenceFact, request);
    }

    private boolean isReferenceFactPath(String path) {
        return "$ref".equals(path) || path.endsWith(".$ref");
    }

    private boolean indexedReferenceMatches(
            Map<String, QueryAttributeFact> factsByPath,
            String refPath,
            QueryAttributeFact refFact,
            TraverseQueryRequestDTO request
    ) {
        Object value = refFact.getValue();
        if (!(value instanceof String ref)) {
            return false;
        }

        String[] refParts = ref.split("/");
        if (refParts.length < 2 || refParts.length > 3) {
            return false;
        }

        if (!Objects.equals(request.getSubjectType(), refParts[0])
                || !Objects.equals(request.getDppId(), refParts[1])) {
            return false;
        }

        Integer referencedRevision = indexedRevisionNumber(factsByPath, refPath, refParts);
        return request.getRevisionNumber() == null
                || Objects.equals(request.getRevisionNumber(), referencedRevision);
    }

    private Integer indexedRevisionNumber(
            Map<String, QueryAttributeFact> factsByPath,
            String refPath,
            String[] refParts
    ) {
        if (refParts.length == 3) {
            try {
                return Integer.valueOf(refParts[2]);
            } catch (NumberFormatException ignored) {
                return null;
            }
        }

        QueryAttributeFact versionFact = factsByPath.get(siblingVersionPath(refPath));
        if (versionFact == null || versionFact.getValueNumber() == null) {
            return null;
        }

        return versionFact.getValueNumber().intValue();
    }

    private String siblingVersionPath(String refPath) {
        if ("$ref".equals(refPath)) {
            return "version";
        }

        return refPath.substring(0, refPath.length() - ".$ref".length()) + ".version";
    }

    private BigDecimal requireNumericFact(QueryAttributeFact fact) {
        if (fact.getValueNumber() != null) {
            return fact.getValueNumber();
        }

        throw new IllegalArgumentException("Aggregate value is not numeric for path: " + fact.getPath());
    }

    /**
     * Returns SELECT rows as flat path-value maps, applying both filters and requested return fields in the repository.
     */
    private Stream<Map<String, Object>> matchingSelectedFactValues(PredicateQueryRequestDTO request) {
        return factsGroupedByDpp(request, request.getReturnFields())
                .values()
                .stream()
                .map(this::factValuesByPath);
    }

    /**
     * Returns complete matching fact groups for COUNT and SUM; return fields are intentionally ignored here.
     */
    private Stream<Map<String, QueryAttributeFact>> matchingFactGroups(PredicateQueryRequestDTO request) {
        return factsGroupedByDpp(request, null).values().stream();
    }

    /**
     * Loads DB-filtered facts for a predicate request and groups them by logical DPP ID and path.
     *
     * @param returnFields optional SELECT projection; pass {@code null} when full fact groups are required
     */
    private Map<String, Map<String, QueryAttributeFact>> factsGroupedByDpp(
            PredicateQueryRequestDTO request,
            List<String> returnFields
    ) {
        return groupFactsByDpp(queryAttributeFactRepository.findAllBySubjectTypesNameAndFilters(
                request.getSubjectTypes(),
                request.getFilters(),
                returnFields
        ));
    }

    /**
     * Loads all facts for a source subject type and groups them for in-memory traverse matching.
     */
    private Map<String, Map<String, QueryAttributeFact>> factsGroupedByDpp(String subjectType) {
        return groupFactsByDpp(queryAttributeFactRepository.findAllBySubjectTypeName(subjectType));
    }

    /**
     * Groups flat fact rows into logical DPP records keyed by query path.
     */
    private Map<String, Map<String, QueryAttributeFact>> groupFactsByDpp(List<QueryAttributeFact> facts) {
        Map<String, Map<String, QueryAttributeFact>> result = new LinkedHashMap<>();

        for (QueryAttributeFact fact : facts) {
            String logicalDppId = fact.getId().getLogicalDppId();
            result.computeIfAbsent(logicalDppId, ignored -> new LinkedHashMap<>())
                    .put(fact.getPath(), fact);
        }

        return result;
    }

    /**
     * Converts one grouped fact record into the flat path-value response representation.
     */
    private Map<String, Object> factValuesByPath(Map<String, QueryAttributeFact> factsByPath) {
        Map<String, Object> result = new LinkedHashMap<>();
        factsByPath.forEach((path, fact) -> result.put(path, fact.getValue()));
        return result;
    }
}
