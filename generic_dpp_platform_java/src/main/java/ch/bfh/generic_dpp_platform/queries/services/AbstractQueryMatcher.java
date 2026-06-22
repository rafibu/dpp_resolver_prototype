package ch.bfh.generic_dpp_platform.queries.services;

import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import ch.bfh.generic_dpp_platform.admin.services.PlatformConfigService;
import ch.bfh.generic_dpp_platform.queries.dtos.PredicateQueryRequestDTO;
import ch.bfh.generic_dpp_platform.queries.dtos.PredicateQueryResponseDTO;
import ch.bfh.generic_dpp_platform.queries.dtos.TraverseQueryRequestDTO;
import ch.bfh.generic_dpp_platform.queries.dtos.TraverseQueryResponseDTO;
import lombok.RequiredArgsConstructor;

import java.util.List;

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

    public TraverseQueryResponseDTO traverse(TraverseQueryRequestDTO request) {
        String platformId = platformConfigService.getPlatformConfig().getIssuerId();
        return TraverseQueryResponseDTO.builder()
                .platformId(platformId)
                .subjectType(request.getSubjectType())
                .dppId(request.getDppId())
                .matches(executeTraverseQuery(request))
                .build();
    }

    /**
     * Executes a query to match predicate conditions based on the given request.
     *
     * @param request the request object containing the query details
     * @return an object representing the matching results, which can vary based on the
     *         implementation and the result mode specified in the request.
     */
    protected abstract Object queryMatches(PredicateQueryRequestDTO request);

    /**
     * Executes a query to count the number of records matching the specified predicate conditions
     * based on the provided request.
     *
     * @param request the request object containing the query details
     * @return the count of records that match the specified query conditions.
     */
    protected abstract Long queryCount(PredicateQueryRequestDTO request);

    /**
     * Executes a query to compute the sum of values for a specified field or path based on the provided
     * predicate conditions in the request.
     *
     * @param request the request object containing the query details, including the field to aggregate.
     * @return the computed sum of the values for the specified field or path, matching the query conditions;
     *         or {@code null} if no matching records are found or the field is invalid.
     */
    protected abstract Double querySum(PredicateQueryRequestDTO request);

    protected abstract List<Object> executeTraverseQuery(TraverseQueryRequestDTO request);
}
