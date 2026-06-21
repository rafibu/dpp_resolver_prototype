package ch.bfh.generic_dpp_platform.queries.services;

import ch.bfh.generic_dpp_platform.queries.dtos.PredicateQueryRequestDTO;
import ch.bfh.generic_dpp_platform.queries.dtos.PredicateQueryResponseDTO;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

/**
 *
 * @author rbu on 19.06.2026
 */

@Service
@RequiredArgsConstructor
public class PredicateQueryService {

    private final IndexedQueryMatcher indexedQueryMatcher;
    private final OnDemandQueryMatcher onDemandQueryMatcher;

    public PredicateQueryResponseDTO queryPredicate(PredicateQueryRequestDTO request) {
        validateRequest(request);

        return switch (request.getExecutionMode()) {
            case INDEXED -> indexedQueryMatcher.queryPredicate(request);
            case ON_DEMAND -> onDemandQueryMatcher.queryPredicate(request);
        };
    }

    private void validateRequest(PredicateQueryRequestDTO request) {
        if (request.getResultMode() == null) {
            throw new IllegalArgumentException("result_mode is required");
        }

        if (request.getExecutionMode() == null) {
            throw new IllegalArgumentException("execution_mode is required");
        }

        if (request.getSubjectType() == null || request.getSubjectType().isBlank()) {
            throw new IllegalArgumentException("subject_type is required");
        }

        switch (request.getResultMode()) {
            case SUM -> {
                if (request.getAggregatePath() == null || request.getAggregatePath().isBlank()) {
                    throw new IllegalArgumentException("aggregate_path is required for SUM queries");
                }
            }
            case SELECT, COUNT -> {
                if (request.getAggregatePath() != null && !request.getAggregatePath().isBlank()) {
                    throw new IllegalArgumentException("aggregate_path is only supported for SUM queries");
                }
            }
        }
    }
}
