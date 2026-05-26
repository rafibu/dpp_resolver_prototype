package ch.bfh.generic_dpp_platform.admin.dtos;

import lombok.Data;

/**
 * DTO for platform configuration, used for initialization in the factory
 *
 * @author rbu on 21.04.2026
 */
@Data
public class PlatformConfigDTO {
    private String platformName;
    private String baseUrl;
    private String issuerId;
    private String resolverBaseUrl;
}
