package ch.bfh.generic_dpp_platform.queries.dtos;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

/**
 *
 * @author rbu on 22.06.2026
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class TraverseQueryRequestDTO {

    @NotBlank
    private String subjectType;

    @NotBlank
    private String dppId;

    @Builder.Default
    private QueryExecutionMode executionMode = QueryExecutionMode.INDEXED;

    /**
     * Optional. If present, the query searches for hard references
     * to this exact target revision.
     */
    private Integer revisionNumber;

    /**
     * Source subject types and reference paths to inspect.
     */
    @Valid
    @NotNull
    private List<TraverseSourceScopeDTO> sources;

}
