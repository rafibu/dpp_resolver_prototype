package ch.bfh.generic_dpp_platform.queries.services;

import ch.bfh.generic_dpp_platform.queries.dtos.TraverseQueryRequestDTO;
import ch.bfh.generic_dpp_platform.queries.dtos.TraverseQueryResponseDTO;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;


/**
 * Coordinates platform-local reverse traversal over DPP references.
 *
 * <p>The caller supplies source subject types and optional reference paths,
 * normally derived from the resolver's schema dependency graph. This service
 * selects indexed or on-demand matching but does not perform federation-wide
 * routing.</p>
 */
@Service
@RequiredArgsConstructor
public class TraverseQueryService {


    private final IndexedQueryMatcher indexedQueryMatcher;
    private final OnDemandQueryMatcher onDemandQueryMatcher;

    /**
     * Validates and executes one local reverse-traversal request.
     *
     * @param request the target logical DPP or revision and source scope
     * @return current local source records that reference the target
     */
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
