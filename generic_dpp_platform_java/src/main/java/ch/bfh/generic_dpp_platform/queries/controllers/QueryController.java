package ch.bfh.generic_dpp_platform.queries.controllers;

import ch.bfh.generic_dpp_platform.queries.dtos.PredicateQueryRequestDTO;
import ch.bfh.generic_dpp_platform.queries.dtos.PredicateQueryResponseDTO;
import ch.bfh.generic_dpp_platform.queries.dtos.TraverseQueryRequestDTO;
import ch.bfh.generic_dpp_platform.queries.dtos.TraverseQueryResponseDTO;
import ch.bfh.generic_dpp_platform.queries.services.PredicateQueryService;
import ch.bfh.generic_dpp_platform.queries.services.TraverseQueryService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * HTTP boundary for platform-local derived query access.
 *
 * <p>Predicate retrieval and reverse traversal are evaluated by the platform
 * that hosts the candidate revisions. Federation-wide routing, schema-level
 * source scoping, and result merging are performed by callers outside this
 * controller.</p>
 */
@Slf4j
@RestController
@RequestMapping("/query")
@RequiredArgsConstructor
public class QueryController {

    private final PredicateQueryService predicateQueryService;
    private final TraverseQueryService traverseQueryService;

    /**
     * Evaluates predicate retrieval over this platform's current revisions.
     *
     * @param request the platform-local query, bound from query parameters
     * @return selected attribute facts, a count, or a sum for the local candidates
     */
    @GetMapping("/predicate")
    public ResponseEntity<PredicateQueryResponseDTO> queryPredicate(
            @Valid @ModelAttribute PredicateQueryRequestDTO request) {
        log.info("Querying predicate: {}", request);
        return ResponseEntity.ok(predicateQueryService.queryPredicate(request));
    }

    /**
     * Finds current source revisions that reference a target logical DPP or revision.
     *
     * @param request the target and externally supplied schema-level source scope
     * @return the matching source records hosted by this platform
     */
    @GetMapping("/traverse")
    public ResponseEntity<TraverseQueryResponseDTO> queryTraverse(
            @Valid @ModelAttribute TraverseQueryRequestDTO request
    ){
        log.info("Querying traverse: {}", request);
        return ResponseEntity.ok(traverseQueryService.queryTraverse(request));
    }

}
