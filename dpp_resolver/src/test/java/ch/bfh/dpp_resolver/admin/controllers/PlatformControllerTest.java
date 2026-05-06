package ch.bfh.dpp_resolver.admin.controllers;

import ch.bfh.dpp_resolver.ControllerTest;
import ch.bfh.dpp_resolver.admin.dto.PlatformMappingDTO;
import ch.bfh.dpp_resolver.admin.dto.SubjectTypeDTO;
import com.google.gson.Gson;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;

import static org.junit.jupiter.api.Assertions.*;

class PlatformControllerTest extends ControllerTest {

    private final Gson gson = new Gson();

    @Test
    void getAllPlatformMappings_shouldReturnEmptyArray() throws Exception {
        PlatformMappingDTO[] result = getResponseAsObject("/admin/platforms", PlatformMappingDTO[].class);
        assertEquals(0, result.length);
    }

    @Test
    void createAndGetPlatformMappings_happyPath() throws Exception {
        // 1. Create SubjectType
        SubjectTypeDTO st = new SubjectTypeDTO("Car", "Automobile");
        postResponseAsObject("/admin/subject-types", gson.toJson(st), SubjectTypeDTO.class);

        // 2. Create PlatformMapping
        PlatformMappingDTO mapping = PlatformMappingDTO.builder()
                .subjectTypes(java.util.List.of("Car"))
                .platform("EuroTax")
                .issuerId("ET")
                .resolutionUrl("https://eurotax.com/res/")
                .build();
        
        PlatformMappingDTO created = postResponseAsObject("/admin/platforms", gson.toJson(mapping), PlatformMappingDTO.class);
        assertTrue(created.getSubjectTypes().contains("Car"));
        assertEquals("EuroTax", created.getPlatform());

        // 3. Get all
        PlatformMappingDTO[] all = getResponseAsObject("/admin/platforms", PlatformMappingDTO[].class);
        assertEquals(1, all.length);
        assertEquals("ET", all[0].getIssuerId());

        // 4. Get by SubjectType
        PlatformMappingDTO[] byType = getResponseAsObject("/admin/platforms/Car", PlatformMappingDTO[].class);
        assertEquals(1, byType.length);
        assertEquals("EuroTax", byType[0].getPlatform());
    }

    @Test
    void getPlatformMappings_shouldReturnNotFound_whenSubjectTypeDoesNotExist() throws Exception {
        getErrorStatusCode("/admin/platforms/Unknown", HttpStatus.NOT_FOUND);
    }

    @Test
    void createPlatformMapping_shouldReturnBadRequest_whenSubjectTypeDoesNotExist() throws Exception {
        PlatformMappingDTO mapping = PlatformMappingDTO.builder()
                .subjectTypes(java.util.List.of("Unknown"))
                .platform("SomePlatform")
                .build();
        
        postErrorStatusCode("/admin/platforms", gson.toJson(mapping), HttpStatus.BAD_REQUEST);
    }
}
