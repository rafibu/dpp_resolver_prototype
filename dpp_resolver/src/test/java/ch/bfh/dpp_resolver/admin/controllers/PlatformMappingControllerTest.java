package ch.bfh.dpp_resolver.admin.controllers;

import ch.bfh.dpp_resolver.ControllerTest;
import ch.bfh.dpp_resolver.admin.dto.PlatformMappingDTO;
import ch.bfh.dpp_resolver.admin.dto.SubjectTypeDTO;
import ch.bfh.dpp_resolver.admin.repositories.PlatformMappingRepository;
import ch.bfh.dpp_resolver.admin.repositories.SubjectTypeRepository;
import com.google.gson.Gson;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;

import static org.junit.jupiter.api.Assertions.*;

class PlatformMappingControllerTest extends ControllerTest {

    @Autowired
    private PlatformMappingRepository platformMappingRepository;

    @Autowired
    private SubjectTypeRepository subjectTypeRepository;

    private final Gson gson = new Gson();

    @AfterEach
    void tearDown() {
        platformMappingRepository.deleteAll();
        subjectTypeRepository.deleteAll();
    }

    @Test
    void getAllPlatformMappings_shouldReturnEmptyArray() throws Exception {
        PlatformMappingDTO[] result = getResponseAsObject("/admin/mappings", PlatformMappingDTO[].class);
        assertEquals(0, result.length);
    }

    @Test
    void createAndGetPlatformMappings_happyPath() throws Exception {
        // 1. Create SubjectType
        SubjectTypeDTO st = new SubjectTypeDTO("Car", "Automobile");
        postResponseAsObject("/admin/subject-types", gson.toJson(st), SubjectTypeDTO.class);

        // 2. Create PlatformMapping
        PlatformMappingDTO mapping = PlatformMappingDTO.builder()
                .subjectType("Car")
                .platform("EuroTax")
                .abbreviation("ET")
                .resolutionUrl("https://eurotax.com/res/")
                .build();
        
        PlatformMappingDTO created = postResponseAsObject("/admin/mappings", gson.toJson(mapping), PlatformMappingDTO.class);
        assertEquals("Car", created.getSubjectType());
        assertEquals("EuroTax", created.getPlatform());

        // 3. Get all
        PlatformMappingDTO[] all = getResponseAsObject("/admin/mappings", PlatformMappingDTO[].class);
        assertEquals(1, all.length);
        assertEquals("ET", all[0].getAbbreviation());

        // 4. Get by SubjectType
        PlatformMappingDTO[] byType = getResponseAsObject("/admin/mappings/Car", PlatformMappingDTO[].class);
        assertEquals(1, byType.length);
        assertEquals("EuroTax", byType[0].getPlatform());
    }

    @Test
    void getPlatformMappings_shouldReturnNotFound_whenSubjectTypeDoesNotExist() throws Exception {
        getErrorStatusCode("/admin/mappings/Unknown", HttpStatus.NOT_FOUND);
    }

    @Test
    void createPlatformMapping_shouldReturnBadRequest_whenSubjectTypeDoesNotExist() throws Exception {
        PlatformMappingDTO mapping = PlatformMappingDTO.builder()
                .subjectType("Unknown")
                .platform("SomePlatform")
                .build();
        
        postErrorStatusCode("/admin/mappings", gson.toJson(mapping), HttpStatus.BAD_REQUEST);
    }
}
