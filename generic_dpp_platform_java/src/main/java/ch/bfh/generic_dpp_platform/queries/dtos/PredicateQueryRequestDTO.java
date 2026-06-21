package ch.bfh.generic_dpp_platform.queries.dtos;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.ArrayList;
import java.util.List;

/**
 * Request DTO for a platform-local predicate query over DPP revision payloads.
 * <p>
 * The request defines the desired {@link QueryResultMode result mode}, the {@link QueryExecutionMode execution mode},
 * the candidate subject type, optional predicate filters, optional return fields, and an optional aggregate path.
 * It describes what the receiving platform should evaluate against its local candidate set, but it does not model
 * federation-level query orchestration.
 * </p>
 * <p>
 * Federation routing, platform fan-out, result merging, and cross-platform aggregation are handled outside this DTO.
 * This class only represents the query fragment executed by one platform after the relevant candidates have
 * been selected for local evaluation.
 * </p>
 */
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Data
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class PredicateQueryRequestDTO {

    @NotNull
    private QueryResultMode resultMode;

    @NotNull
    @Builder.Default
    private QueryExecutionMode executionMode = QueryExecutionMode.INDEXED;

    /**
     * The subject type of the DPPs to query.
     */
    @NotNull
    private String subjectType;

    /**
     * A list of filters that define the conditions applied to the queried data.<br>
     * All Filters are AND-connected. <br>
     * If no filters are specified, all DPPs will be returned.
     */
    @Valid
    @Builder.Default
    private List<PredicateFilterDTO> filters = new ArrayList<>();

    /**
     * Defines what fields should be returned in the result.
     * If not specified, all fields will be returned.
     * This is only supported for {@link QueryResultMode#SELECT}
     */
    private List<String> returnFields;

    /**
     * The path to the field to aggregate on, if it is a nested field the path must be separated by dots
     * E.g. "aggregate": "material_composition.mass_kg"
     * This is only supported for {@link QueryResultMode#SUM}
     */
    private String aggregatePath;

}
