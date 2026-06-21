package ch.bfh.generic_dpp_platform.queries.dtos;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import jakarta.validation.constraints.NotNull;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.util.List;

/**
 * Response of a predicate query.
 *
 * @author rbu on 19.06.2026
 */
@Builder
@Getter
@NoArgsConstructor
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class PredicateQueryResponseDTO {

    /**
     * The {@link QueryResultMode} actually used for the query.
     * Should be the same as the one specified in the request.
     */
    @NotNull
    private QueryResultMode resultMode;

    /**
     * The {@link QueryExecutionMode} actually used for the query.
     */
    @NotNull
    private QueryExecutionMode executionMode;

    /**
     * The platformId of this platform instance.
     */
    @NotNull
    private String platformId;

    /**
     * If @{@link QueryResultMode#COUNT} is used, this contains the count of matching revisions.
     */
    private Long count;

    /**
     * If @{@link QueryResultMode#SUM} is used, this contains the sum of the specified field.
     */
    private Double aggregate;

    /**
     * If @{@link QueryResultMode#SELECT} is used, this contains the matching revisions.
     */
    private Object matches;

    /**
     * AllArgsConstructor for the builder with sanity check
     */
    public PredicateQueryResponseDTO(QueryResultMode resultMode, QueryExecutionMode executionMode, String platformId, Long count, Double aggregate, Object matches) {
        this.resultMode = resultMode;
        this.executionMode = executionMode;
        this.platformId = platformId;

        if (resultMode == QueryResultMode.COUNT) {
            this.count = count;
            validateIsNull(aggregate, "aggregate");
            validateIsNull(matches, "matches");
        }
        if (resultMode == QueryResultMode.SUM) {
            this.aggregate = aggregate;
            validateIsNull(count, "count");
            validateIsNull(matches, "matches");
        }
        if (resultMode == QueryResultMode.SELECT) {
            this.matches = matches;
            validateIsNull(count, "count");
            validateIsNull(aggregate, "aggregate");
        }
    }

    /**
     * Creates an empty result. Used for queries that do not pertain to this platform,
     * e.g., because the subject type is not handled on this platform.
     *
     * @param request    the {@link PredicateQueryRequestDTO} containing the desired query configurations.
     * @param platformId the unique identifier of the platform instance.
     * @return a {@link PredicateQueryResponseDTO} with the provided query result mode, execution mode,
     * and platform ID and an empty result appropriate for the requested mode.
     */
    public static PredicateQueryResponseDTO empty(PredicateQueryRequestDTO request, String platformId) {
        return switch (request.getResultMode()) {
            case SELECT -> new PredicateQueryResponseDTO(
                    request.getResultMode(), request.getExecutionMode(), platformId, null, null, List.of());
            case COUNT -> new PredicateQueryResponseDTO(
                    request.getResultMode(), request.getExecutionMode(), platformId, 0L, null, null);
            case SUM -> new PredicateQueryResponseDTO(
                    request.getResultMode(), request.getExecutionMode(), platformId, null, 0.0, null);
        };
    }

    private void validateIsNull(Object value, String fieldName) {
        if (value != null) {
            throw new IllegalArgumentException("Invalid query result mode: " + resultMode + ". " + fieldName + " must be null.");
        }
    }
}
