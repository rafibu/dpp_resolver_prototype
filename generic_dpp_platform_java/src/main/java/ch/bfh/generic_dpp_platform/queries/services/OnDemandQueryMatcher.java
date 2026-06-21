package ch.bfh.generic_dpp_platform.queries.services;

import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import ch.bfh.generic_dpp_platform.admin.services.PlatformConfigService;
import ch.bfh.generic_dpp_platform.dpps.models.DppRevision;
import ch.bfh.generic_dpp_platform.dpps.models.LogicalDpp;
import ch.bfh.generic_dpp_platform.dpps.repositories.DppRevisionRepository;
import ch.bfh.generic_dpp_platform.dpps.repositories.LogicalDppRepository;
import ch.bfh.generic_dpp_platform.queries.dtos.PredicateQueryRequestDTO;
import ch.bfh.generic_dpp_platform.queries.helpers.PredicateQueryHelper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Stream;

/**
 *
 * @author rbu on 21.06.2026
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

    @Override
    @Transactional(readOnly = true)
    protected Object queryMatches(PredicateQueryRequestDTO request) {
        return matchingDocuments(request)
                .map(document -> PredicateQueryHelper.selectFields(document, request.getReturnFields()))
                .toList();
    }

    @Override
    @Transactional(readOnly = true)
    protected Long queryCount(PredicateQueryRequestDTO request) {
        return matchingDocuments(request).count();
    }

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

    private Stream<Map<String, Object>> matchingDocuments(PredicateQueryRequestDTO request) {
        return getAllDppsForSubjectType(request.getSubjectType()).stream()
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


    private List<LogicalDpp> getAllDppsForSubjectType(String subjectType) {
        SubjectType subjectTypeEntity = subjectTypeRepository.findByName(subjectType)
                .orElseThrow(() -> new IllegalArgumentException("Subject type not found: " + subjectType));
        return dppRepository.findAllBySubjectType(subjectTypeEntity);
    }

    private DppRevision getLatestRevisionForDpp(LogicalDpp dpp) {
        return dppRevisionRepository.findCurrentByDppId(dpp.getDppId())
                .orElseThrow(() -> new IllegalArgumentException("No revision found for DppId: " + dpp.getDppId()));
    }
}
