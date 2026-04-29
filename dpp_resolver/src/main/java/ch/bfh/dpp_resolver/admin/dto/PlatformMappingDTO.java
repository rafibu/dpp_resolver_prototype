package ch.bfh.dpp_resolver.admin.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 *
 * @author rbu on 20.04.2026
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class PlatformMappingDTO {
    String subjectType;
    String platform;
    String abbreviation;
    String resolutionUrl;
}
