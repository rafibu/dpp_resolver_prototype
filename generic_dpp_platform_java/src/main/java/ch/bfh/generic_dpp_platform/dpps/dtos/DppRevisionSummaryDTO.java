package ch.bfh.generic_dpp_platform.dpps.dtos;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Summary of a DPP revision used in the response of GET /dpps/{dppId}/revisions.
 *
 * @author rbu on 02.05.2026
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
    private Object payload;
}
