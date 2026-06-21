package ch.bfh.generic_dpp_platform.queries.controllers;

import ch.bfh.generic_dpp_platform.queries.dtos.PredicateQueryRequestDTO;
import ch.bfh.generic_dpp_platform.queries.dtos.PredicateQueryResponseDTO;
import ch.bfh.generic_dpp_platform.queries.services.PredicateQueryService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 *
 * @author rbu on 19.06.2026
 */
@Slf4j
@RestController
@RequestMapping("/query")
@RequiredArgsConstructor
public class QueryController {

    private final PredicateQueryService predicateQueryService;

    @GetMapping("/predicate")
    public ResponseEntity<PredicateQueryResponseDTO> queryPredicate(
            @Valid @ModelAttribute PredicateQueryRequestDTO request) {
        log.info("Querying predicate: {}", request);
        return ResponseEntity.ok(predicateQueryService.queryPredicate(request));
    }

}
