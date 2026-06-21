package ch.bfh.generic_dpp_platform.queries.services;

import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import ch.bfh.generic_dpp_platform.admin.services.PlatformConfigService;
import ch.bfh.generic_dpp_platform.queries.dtos.PredicateQueryRequestDTO;
import ch.bfh.generic_dpp_platform.queries.dtos.PredicateQueryResponseDTO;
import lombok.RequiredArgsConstructor;

/**
 *
 * @author rbu on 21.06.2026
 */
@RequiredArgsConstructor
public abstract class AbstractQueryMatcher {
    private final PlatformConfigService platformConfigService;

    private final SubjectTypeRepository subjectTypeRepository;

    public PredicateQueryResponseDTO queryPredicate(PredicateQueryRequestDTO request) {
        String platformId = platformConfigService.getPlatformConfig().getIssuerId();

        if(!subjectTypeRepository.existsByName(request.getSubjectType())) {
            return PredicateQueryResponseDTO.empty(request, platformId);
        }

        return switch (request.getResultMode()) {
            case SELECT -> PredicateQueryResponseDTO.builder()
                    .resultMode(request.getResultMode())
                    .executionMode(request.getExecutionMode())
                    .platformId(platformId)
                    .matches(queryMatches(request))
                    .build();

            case COUNT -> PredicateQueryResponseDTO.builder()
                    .resultMode(request.getResultMode())
                    .executionMode(request.getExecutionMode())
                    .platformId(platformId)
                    .count(queryCount(request))
                    .build();

            case SUM -> PredicateQueryResponseDTO.builder()
                    .resultMode(request.getResultMode())
                    .executionMode(request.getExecutionMode())
                    .platformId(platformId)
                    .aggregate(querySum(request))
                    .build();
        };
    }

    protected abstract Object queryMatches(PredicateQueryRequestDTO request);

    protected abstract Long queryCount(PredicateQueryRequestDTO request);

    protected abstract Double querySum(PredicateQueryRequestDTO request);
}
