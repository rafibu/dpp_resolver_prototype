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
 * Common result shaping for the two local derived-query execution strategies.
 *
 * <p>Implementations provide equivalent predicate retrieval and reverse
 * traversal semantics over either current payloads or materialized attribute
 * facts. This class adds the platform identity and turns the requested result
 * mode into a local SELECT, COUNT, or SUM response.</p>
 */
@RequiredArgsConstructor
public abstract class AbstractQueryMatcher {
    private final PlatformConfigService platformConfigService;

    private final SubjectTypeRepository subjectTypeRepository;

    /**
     * Executes platform-local predicate retrieval in the requested result mode.
     *
     * @param request the validated predicate-retrieval request
     * @return a response tied to this platform, or an empty result for an unknown subject type
     */
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

    /**
     * Executes reverse traversal within the source scopes supplied by the caller.
     *
     * @param request the target logical DPP or revision and source subject-type scope
     * @return local source records whose references match the target
     */
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
     * Returns projected fields for current local revisions satisfying every predicate.
     *
     * @param request the predicate-retrieval request
     * @return one projected result per matching local revision
     */
    protected abstract Object queryMatches(PredicateQueryRequestDTO request);

    /**
     * Counts current local revisions satisfying every predicate.
     *
     * @param request the predicate-retrieval request
     * @return the local matching-revision count
     */
    protected abstract Long queryCount(PredicateQueryRequestDTO request);

    /**
     * Sums a numeric attribute over current local revisions satisfying every predicate.
     *
     * @param request the predicate-retrieval request with an aggregate path
     * @return the local aggregate, with missing values omitted
     */
    protected abstract Double querySum(PredicateQueryRequestDTO request);

    /**
     * Finds local source documents whose references match the requested target.
     *
     * @param request the target and schema-level source scope
     * @return the matching source records
     */
    protected abstract List<Object> executeTraverseQuery(TraverseQueryRequestDTO request);
}
