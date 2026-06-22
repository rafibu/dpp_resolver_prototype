package ch.bfh.generic_dpp_platform.queries.services;

import ch.bfh.generic_dpp_platform.queries.dtos.TraverseQueryRequestDTO;
import ch.bfh.generic_dpp_platform.queries.dtos.TraverseQueryResponseDTO;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;


/**
 *
 * @author rbu on 22.06.2026
 */
@Service
@RequiredArgsConstructor
public class TraverseQueryService {


    private final IndexedQueryMatcher indexedQueryMatcher;
    private final OnDemandQueryMatcher onDemandQueryMatcher;

    public TraverseQueryResponseDTO queryTraverse(@Valid TraverseQueryRequestDTO request) {
        validateRequest(request);

        return switch (request.getExecutionMode()) {
            case INDEXED -> indexedQueryMatcher.traverse(request);
            case ON_DEMAND -> onDemandQueryMatcher.traverse(request);
        };
    }

    private void validateRequest(TraverseQueryRequestDTO request) {
        if(request.getDppId() == null || request.getDppId().isBlank()){
            throw new IllegalArgumentException("dpp_id is required");
        }
        if(request.getSubjectType() == null || request.getSubjectType().isBlank()){
            throw new IllegalArgumentException("subject_type is required");
        }
    }
}
