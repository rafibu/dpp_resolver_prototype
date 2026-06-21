package ch.bfh.generic_dpp_platform.queries.services;

import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import ch.bfh.generic_dpp_platform.admin.services.PlatformConfigService;
import ch.bfh.generic_dpp_platform.queries.dtos.PredicateFilterDTO;
import ch.bfh.generic_dpp_platform.queries.dtos.PredicateQueryRequestDTO;
import ch.bfh.generic_dpp_platform.queries.models.QueryAttributeFact;
import ch.bfh.generic_dpp_platform.queries.repositories.QueryAttributeFactRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Stream;

/**
 *
 * @author rbu on 21.06.2026
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

    @Override
    @Transactional(readOnly = true)
    protected Object queryMatches(PredicateQueryRequestDTO request) {
        return matchingFactGroups(request)
                .map(factsByPath -> selectFields(factsByPath, request.getReturnFields()))
                .toList();
    }

    @Override
    @Transactional(readOnly = true)
    protected Long queryCount(PredicateQueryRequestDTO request) {
        return matchingFactGroups(request).count();
    }

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