package ch.bfh.generic_dpp_platform.dpps.dtos;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

/**
 * Full DPP detail with all revisions as returned by GET /dpps/:id.
 *
 * @author rbu on 21.04.2026
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class DppDetailDTO {
    private String dppId;
    private String subjectType;
    private List<DppRevisionSummaryDTO> revisions;
}
