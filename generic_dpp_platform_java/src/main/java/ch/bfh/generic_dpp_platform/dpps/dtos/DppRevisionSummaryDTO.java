package ch.bfh.generic_dpp_platform.dpps.dtos;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * A single revision summary inside DppDetailDTO.
 * schema_ref format: "subjectType/major.minor"
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class DppRevisionSummaryDTO {
    private Integer version;
    private String schemaRef;
    private String hash;
    private String timestamp;
    private Object payload;
}
