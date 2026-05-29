package ch.bfh.dpp_resolver.admin.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

/**
 *
 * @author rbu on 20.04.2026
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class PlatformMappingDTO {
    String platform;
    String issuerId;
    String resolutionUrl;
    List<String> subjectTypes;
}
