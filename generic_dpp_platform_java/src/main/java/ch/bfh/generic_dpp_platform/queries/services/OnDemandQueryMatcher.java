package ch.bfh.generic_dpp_platform.queries.services;

import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import ch.bfh.generic_dpp_platform.admin.services.PlatformConfigService;
import ch.bfh.generic_dpp_platform.dpps.models.DppRevision;
import ch.bfh.generic_dpp_platform.dpps.models.LogicalDpp;
import ch.bfh.generic_dpp_platform.dpps.repositories.DppRevisionRepository;
import ch.bfh.generic_dpp_platform.dpps.repositories.LogicalDppRepository;
import ch.bfh.generic_dpp_platform.queries.dtos.PredicateQueryRequestDTO;
import ch.bfh.generic_dpp_platform.queries.dtos.TraverseQueryRequestDTO;
import ch.bfh.generic_dpp_platform.queries.dtos.TraverseSourceScopeDTO;
import ch.bfh.generic_dpp_platform.queries.helpers.PredicateQueryHelper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.LinkedList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Stream;

/**
 * Evaluates local derived queries directly from current revision payloads.
 *
 * <p>This execution strategy scans the candidate revisions, resolves payload
 * paths, and applies predicates or reference matching at request time. It is
 * the semantic baseline for the materialized attribute-fact index.</p>
 */
@Service
public class OnDemandQueryMatcher extends AbstractQueryMatcher {
    private final LogicalDppRepository dppRepository;
    private final SubjectTypeRepository subjectTypeRepository;
    private final DppRevisionRepository dppRevisionRepository;

    public OnDemandQueryMatcher(PlatformConfigService platformConfigService, LogicalDppRepository dppRepository, SubjectTypeRepository subjectTypeRepository, DppRevisionRepository dppRevisionRepository) {
        super(platformConfigService, subjectTypeRepository);
        this.dppRepository = dppRepository;
        this.subjectTypeRepository = subjectTypeRepository;
        this.dppRevisionRepository = dppRevisionRepository;
    }

    /**
     * Selects fields from every current local payload satisfying all filters.
     */
    @Override
    @Transactional(readOnly = true)
    protected Object queryMatches(PredicateQueryRequestDTO request) {
        return matchingDocuments(request)
                .map(document -> PredicateQueryHelper.selectFields(document, request.getReturnFields()))
                .toList();
    }

    /**
     * Counts current local payloads satisfying all filters.
     */
    @Override
    @Transactional(readOnly = true)
    protected Long queryCount(PredicateQueryRequestDTO request) {
        return matchingDocuments(request).count();
    }

    /**
     * Sums a numeric payload field over the matching current local payloads.
     */
    @Override
    @Transactional(readOnly = true)
    protected Double querySum(PredicateQueryRequestDTO request) {
        return matchingDocuments(request)
                .map(document -> PredicateQueryHelper.resolvePath(document, request.getAggregatePath()))
                .filter(Objects::nonNull)
                .map(this::requireNumber)
                .mapToDouble(Number::doubleValue)
                .sum();
    }

    /**
     * Performs reverse traversal by scanning current local source payloads.
     */
    @Override
    @Transactional(readOnly = true)
    protected List<Object> executeTraverseQuery(TraverseQueryRequestDTO request) {
        List<Object> matches = new LinkedList<>();
        for (TraverseSourceScopeDTO sourceScope : request.getSources()) {
            List<Object> scopeMatches = getAllDppsForSubjectTypes(List.of(sourceScope.getSubjectType()))
                    .stream()
                    .map(this::getLatestRevisionForDpp)
                    .map(DppRevision::getDppDocument)
                    .filter(Objects::nonNull)
                    .filter(document -> documentContainsReference(document, sourceScope, request))
                    .map(document -> (Object) document)
                    .toList();

            matches.addAll(scopeMatches);
        }
        return matches;
    }

    private boolean documentContainsReference(
            Map<String, Object> document,
            TraverseSourceScopeDTO sourceScope,
            TraverseQueryRequestDTO request
    ) {
        if (sourceScope.getReferencePaths() == null || sourceScope.getReferencePaths().isEmpty()) {
            return containsMatchingReference(document, request);
        }

        return sourceScope.getReferencePaths()
                .stream()
                .map(path -> PredicateQueryHelper.resolvePath(document, path))
                .anyMatch(value -> containsMatchingReference(value, request));
    }

    private boolean containsMatchingReference(Object value, TraverseQueryRequestDTO request) {
        if (value instanceof Map<?, ?> map) {
            if (map.containsKey("$ref") && referenceMatches(map, request)) {
                return true;
            }

            return map.values()
                    .stream()
                    .anyMatch(child -> containsMatchingReference(child, request));
        }

        if (value instanceof Iterable<?> iterable) {
            for (Object child : iterable) {
                if (containsMatchingReference(child, request)) {
                    return true;
                }
            }
        }

        return false;
    }

    private boolean referenceMatches(Map<?, ?> referenceObject, TraverseQueryRequestDTO request) {
        Object refValue = referenceObject.get("$ref");
        if (!(refValue instanceof String ref)) {
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

        Integer referencedRevision = null;
        if (refParts.length == 3) {
            try {
                referencedRevision = Integer.valueOf(refParts[2]);
            } catch (NumberFormatException ignored) {
                return false;
            }
        } else if (referenceObject.get("version") instanceof Number version) {
            referencedRevision = version.intValue();
        }

        return request.getRevisionNumber() == null
                || Objects.equals(request.getRevisionNumber(), referencedRevision);
    }

    private Stream<Map<String, Object>> matchingDocuments(PredicateQueryRequestDTO request) {
        return getAllDppsForSubjectTypes(request.getSubjectTypes()).stream()
                .map(this::getLatestRevisionForDpp)
                .map(DppRevision::getDppDocument)
                .filter(document -> matchesAllFilters(document, request));
    }

    private boolean matchesAllFilters(Map<String, Object> document, PredicateQueryRequestDTO request) {
        return request.getFilters() == null
                || request.getFilters().isEmpty()
                || request.getFilters().stream().allMatch(filter -> filter.matches(document));
    }

    private Number requireNumber(Object value) {
        if (value instanceof Number number) {
            return number;
        }
        throw new IllegalArgumentException("Aggregate value is not numeric: " + value);
    }


    private List<LogicalDpp> getAllDppsForSubjectTypes(List<String> subjectTypes) {
        List<SubjectType> subjectTypeEntity = subjectTypeRepository.findAllByNameIn(subjectTypes);
        if (subjectTypeEntity.isEmpty()) {
            return List.of();
        }
        return dppRepository.findAllBySubjectTypeIn(subjectTypeEntity);
    }

    private DppRevision getLatestRevisionForDpp(LogicalDpp dpp) {
        return dppRevisionRepository.findCurrentByDppId(dpp.getDppId())
                .orElseThrow(() -> new IllegalArgumentException("No revision found for DppId: " + dpp.getDppId()));
    }
}
