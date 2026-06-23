package ch.bfh.generic_dpp_platform.queries.services;

import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import ch.bfh.generic_dpp_platform.admin.services.PlatformConfigService;
import ch.bfh.generic_dpp_platform.queries.dtos.PredicateFilterDTO;
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
        return matchingFactGroups(request)
                .map(factsByPath -> selectFields(factsByPath, request.getReturnFields()))
                .toList();
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
                    .map(factsByPath -> (Object) selectFields(factsByPath, null))
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

    private Stream<Map<String, QueryAttributeFact>> matchingFactGroups(PredicateQueryRequestDTO request) {
        return factsGroupedByDpp(request.getSubjectType()).values().stream()
                .filter(factsByPath -> matchesAllFilters(factsByPath, request));
    }

    private Map<String, Map<String, QueryAttributeFact>> factsGroupedByDpp(String subjectType) {
        Map<String, Map<String, QueryAttributeFact>> result = new LinkedHashMap<>();

        for (QueryAttributeFact fact : queryAttributeFactRepository.findAllBySubjectTypeName(subjectType)) {
            String logicalDppId = fact.getId().getLogicalDppId();
            result.computeIfAbsent(logicalDppId, ignored -> new LinkedHashMap<>())
                    .put(fact.getPath(), fact);
        }
        return result;
    }

    private boolean matchesAllFilters(Map<String, QueryAttributeFact> factsByPath, PredicateQueryRequestDTO request) {
        return request.getFilters() == null
                || request.getFilters().isEmpty()
                || request.getFilters().stream().allMatch(filter -> matchesFilter(factsByPath, filter));
    }

    private boolean matchesFilter(Map<String, QueryAttributeFact> factsByPath, PredicateFilterDTO filter) {
        QueryAttributeFact fact = factsByPath.get(filter.getPath());
        Object documentValue = fact == null ? null : fact.getValue();

        try {
            return filter.matches(documentValue);
        } catch (IllegalArgumentException exception) {
            throw new IllegalArgumentException(
                    "Invalid indexed filter: " + filter.getPath() + " " + filter.getOperator() + " " + filter.getValue(),
                    exception
            );
        }
    }

    private Map<String, Object> selectFields(Map<String, QueryAttributeFact> factsByPath, List<String> returnFields) {
        Map<String, Object> result = new LinkedHashMap<>();

        if (returnFields == null || returnFields.isEmpty()) {
            factsByPath.forEach((path, fact) -> result.put(path, fact.getValue()));
            return result;
        }

        for (String returnField : returnFields) {
            QueryAttributeFact fact = factsByPath.get(returnField);
            if (fact != null) {
                result.put(returnField, fact.getValue());
            }
        }

        return result;
    }
}
