package ch.bfh.generic_dpp_platform.queries.dtos;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
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
public class TraverseQueryResponseDTO {
    private String platformId;

    private String subjectType;
    private String dppId;

    @Builder.Default
    private List<Object> matches = List.of();
}
