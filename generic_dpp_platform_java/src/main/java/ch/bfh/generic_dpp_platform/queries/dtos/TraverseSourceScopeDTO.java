package ch.bfh.generic_dpp_platform.queries.dtos;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import jakarta.validation.constraints.NotBlank;
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
public class TraverseSourceScopeDTO {

    @NotBlank
    private String subjectType;

    /**
     * Optional restriction to specific materialized reference paths.
     * If omitted or empty, all reference paths for this source subject type are considered.
     */
    private List<String> referencePaths;
}