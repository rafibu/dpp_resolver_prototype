package ch.bfh.generic_dpp_platform.dpps.dtos;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

/**
 * DTO for a bounded hard-reference closure rooted at one DPP revision.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class DppRevisionClosureResponseDTO {
    private DppRevisionResponseDTO rootRevision;
    private List<DppRevisionResponseDTO> resolvedRevisions;
}
