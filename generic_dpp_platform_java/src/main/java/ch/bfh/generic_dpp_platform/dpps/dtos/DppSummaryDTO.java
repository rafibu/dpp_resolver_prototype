package ch.bfh.generic_dpp_platform.dpps.dtos;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Summary of a logical DPP as returned by GET /dpps.
 *
 * @author rbu on 21.04.2026
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class DppSummaryDTO {
    private String dppId;
    private String subjectType;
    private Integer currentVersion;
    private String lastUpdated;
}
