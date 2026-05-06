package ch.bfh.generic_dpp_platform.admin.services;

import ch.bfh.generic_dpp_platform.admin.config.PlatformProperties;
import ch.bfh.generic_dpp_platform.admin.dtos.PlatformConfigDTO;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "platform.platform-name=Test Platform",
        "platform.base-url=http://localhost:8081",
        "platform.issuer-id=issuerA",
        "platform.resolver-base-url=http://localhost:8080"
})
public class PlatformConfigServiceTest {

    @Autowired
    private PlatformConfigService platformConfigService;

    @Autowired
    private PlatformProperties platformProperties;

    @Test
    public void testGetPlatformConfig_ReturnsValuesFromProperties() {
        PlatformConfigDTO config = platformConfigService.getPlatformConfig();

        assertNotNull(config);
        assertEquals("Test Platform", config.getPlatformName());
        assertEquals("http://localhost:8081", config.getBaseUrl());
        assertEquals("issuerA", config.getIssuerId());
        assertEquals("http://localhost:8080", config.getResolverBaseUrl());
        
        // Also verify properties directly
        assertEquals("Test Platform", platformProperties.getPlatformName());
    }
}
