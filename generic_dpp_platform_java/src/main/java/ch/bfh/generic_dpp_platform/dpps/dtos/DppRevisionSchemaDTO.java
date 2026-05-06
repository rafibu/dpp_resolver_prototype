package ch.bfh.generic_dpp_platform.dpps.dtos;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 *
 * @author rbu on 02.05.2026
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class DppRevisionSchemaDTO {
    String subjectType;
    Integer majorVersion;
    Integer minorVersion;
}
