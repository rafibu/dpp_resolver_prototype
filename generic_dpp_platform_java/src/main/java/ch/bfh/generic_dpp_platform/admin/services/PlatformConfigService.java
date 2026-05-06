package ch.bfh.generic_dpp_platform.admin.services;

import ch.bfh.generic_dpp_platform.admin.config.PlatformProperties;
import ch.bfh.generic_dpp_platform.admin.dtos.PlatformConfigDTO;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

/**
 * Service for accessing platform configuration.
 * Configuration is now backed by environment variables through PlatformProperties.
 */
@Service
@RequiredArgsConstructor
public class PlatformConfigService {

    private final PlatformProperties platformProperties;

    public PlatformConfigDTO getPlatformConfig() {
        PlatformConfigDTO dto = new PlatformConfigDTO();
        dto.setPlatformName(platformProperties.getPlatformName());
        dto.setBaseUrl(platformProperties.getBaseUrl());
        dto.setIssuerId(platformProperties.getIssuerId());
        dto.setResolverBaseUrl(platformProperties.getResolverBaseUrl());
        return dto;
    }
}
