package ch.bfh.generic_dpp_platform.admin.controllers;

import ch.bfh.generic_dpp_platform.ControllerTest;
import ch.bfh.generic_dpp_platform.admin.dtos.PlatformConfigDTO;
import ch.bfh.generic_dpp_platform.admin.repositories.PlatformConfigRepository;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

public class PlatformConfigControllerTest extends ControllerTest {

    @Autowired
    private PlatformConfigRepository platformConfigRepository;

    @AfterEach
    public void tearDown() {
        platformConfigRepository.deleteAll();
    }

    @Test
    public void testGetPlatformConfig_HappyPath() throws Exception {
        PlatformConfigDTO response = getResponseAsObject("/admin/platform-config", PlatformConfigDTO.class);
        assertNotNull(response);
    }

    @Test
    public void testSavePlatformConfig_HappyPath() throws Exception {
        PlatformConfigDTO dto = new PlatformConfigDTO();
        dto.setPlatformName("Test Platform");
        dto.setBaseUrl("http://localhost:8080");
        dto.setIssuerId("test-issuer");
        dto.setResolverBaseUrl("http://localhost:8081");

        String json = createGson(false).toJson(dto);

        PlatformConfigDTO response = putResponseAsObject("/admin/platform-config", json, PlatformConfigDTO.class);

        assertNotNull(response);
        assertEquals("Test Platform", response.getPlatformName());
        assertEquals("http://localhost:8080", response.getBaseUrl());
        assertEquals("test-issuer", response.getIssuerId());
        assertEquals("http://localhost:8081", response.getResolverBaseUrl());
        
        // Verify it was actually saved
        PlatformConfigDTO saved = getResponseAsObject("/admin/platform-config", PlatformConfigDTO.class);
        assertEquals("Test Platform", saved.getPlatformName());
    }

    @Test
    public void testSavePlatformConfig_EmptyBody() throws Exception {
        putErrorStatusCode("/admin/platform-config", "", HttpStatus.BAD_REQUEST);
    }

    @Test
    public void testSavePlatformConfig_PartialUpdate() throws Exception {
        // 1. Initial full save
        PlatformConfigDTO initialDto = new PlatformConfigDTO();
        initialDto.setPlatformName("Initial Name");
        initialDto.setBaseUrl("http://initial.url");
        initialDto.setIssuerId("initial-issuer");
        initialDto.setResolverBaseUrl("http://initial-resolver.url");

        putResponseAsObject("/admin/platform-config", createGson(false).toJson(initialDto), PlatformConfigDTO.class);

        // 2. Partial update (only platformName)
        PlatformConfigDTO partialDto = new PlatformConfigDTO();
        partialDto.setPlatformName("Updated Name");
        // Other fields are null

        PlatformConfigDTO response = putResponseAsObject("/admin/platform-config", createGson(false).toJson(partialDto), PlatformConfigDTO.class);

        // 3. Verify
        assertNotNull(response);
        assertEquals("Updated Name", response.getPlatformName());
        assertEquals("http://initial.url", response.getBaseUrl());
        assertEquals("initial-issuer", response.getIssuerId());
        assertEquals("http://initial-resolver.url", response.getResolverBaseUrl());

        // Also verify in DB via GET
        PlatformConfigDTO saved = getResponseAsObject("/admin/platform-config", PlatformConfigDTO.class);
        assertEquals("Updated Name", saved.getPlatformName());
        assertEquals("http://initial.url", saved.getBaseUrl());
    }
}
