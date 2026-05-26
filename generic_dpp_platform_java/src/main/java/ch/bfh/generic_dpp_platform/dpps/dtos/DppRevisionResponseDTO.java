package ch.bfh.generic_dpp_platform.dpps.dtos;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.Date;

/**
 * DTO for DPP revision response if successful.
 *
 * @author rbu on 02.05.2026
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class DppRevisionResponseDTO {
    private String dppId;
    private Integer version;
    private DppRevisionSchemaDTO schemaVersion;
    private Object dppPayload;
    private String payloadHash;
    private Date createdAt;
}
