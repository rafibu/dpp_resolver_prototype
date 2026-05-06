package ch.bfh.generic_dpp_platform.dpps.dtos;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.Date;

/**
 *
 * @author rbu on 02.05.2026
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class DppRevisionResponseDTO {
    private String dppId;
    private Integer version;
    private DppRevisionSchemaDTO schemaVersion;
    private Object dppPayload;
    private String payloadHash;
    private Date createdAt;
}
