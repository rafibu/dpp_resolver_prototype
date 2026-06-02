package ch.bfh.dpp_resolver.admin.controllers;

import ch.bfh.dpp_resolver.ControllerTest;
import ch.bfh.dpp_resolver.admin.dto.PlatformMappingDTO;
import ch.bfh.dpp_resolver.admin.dto.PlatformMigrationRequestDTO;
import ch.bfh.dpp_resolver.admin.dto.SubjectTypeDTO;
import com.google.gson.FieldNamingPolicy;
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class PlatformControllerTest extends ControllerTest {

    private final Gson gson = new GsonBuilder()
            .setFieldNamingPolicy(FieldNamingPolicy.LOWER_CASE_WITH_UNDERSCORES)
            .create();

    private <T> T postOkResponseAsObject(String url, String body, Class<T> clazz) throws Exception {
        String response = sendRequest(post(url).content(body).contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andReturn()
                .getResponse()
                .getContentAsString();
        return gson.fromJson(response, clazz);
    }

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
        
        PlatformMappingDTO created = postResponseAsObject("/admin/platforms/register", gson.toJson(mapping), PlatformMappingDTO.class);
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
    void createPlatformMapping_shouldKeepSourceIssuerSubjectTypes_whenIssuerMigrates() throws Exception {
        postResponseAsObject("/admin/subject-types", gson.toJson(new SubjectTypeDTO("S1", "Subject 1")), SubjectTypeDTO.class);
        postResponseAsObject("/admin/subject-types", gson.toJson(new SubjectTypeDTO("S2", "Subject 2")), SubjectTypeDTO.class);
        postResponseAsObject("/admin/subject-types", gson.toJson(new SubjectTypeDTO("S3", "Subject 3")), SubjectTypeDTO.class);

        PlatformMappingDTO platformA = PlatformMappingDTO.builder()
                .subjectTypes(List.of("S1", "S2"))
                .platform("Platform A")
                .issuerId("platA")
                .resolutionUrl("https://platform-a.example/dpps/{dppId}")
                .build();
        postResponseAsObject("/admin/platforms/register", gson.toJson(platformA), PlatformMappingDTO.class);

        PlatformMappingDTO platformB = PlatformMappingDTO.builder()
                .subjectTypes(List.of("S2", "S3"))
                .platform("Platform B")
                .issuerId("platB")
                .resolutionUrl("https://platform-b.example/dpps/{dppId}")
                .build();
        postResponseAsObject("/admin/platforms/register", gson.toJson(platformB), PlatformMappingDTO.class);

        PlatformMigrationRequestDTO migration = PlatformMigrationRequestDTO.builder()
                .platform("Platform B")
                .newResolutionUrl("https://platform-b.example/dpps/{dppId}")
                .build();
        PlatformMappingDTO result = postOkResponseAsObject("/admin/platforms/platA/migrate", gson.toJson(migration), PlatformMappingDTO.class);

        assertEquals("Platform B", result.getPlatform());
        assertEquals("https://platform-b.example/dpps/{dppId}", result.getResolutionUrl());
        assertTrue(result.getSubjectTypes().contains("S1"));
        assertTrue(result.getSubjectTypes().contains("S2"));
        assertFalse(result.getSubjectTypes().contains("S3"));

        PlatformMappingDTO[] all = getResponseAsObject("/admin/platforms", PlatformMappingDTO[].class);
        assertEquals(2, all.length);

        PlatformMappingDTO[] s1Mappings = getResponseAsObject("/admin/platforms/S1", PlatformMappingDTO[].class);
        assertEquals(1, s1Mappings.length);
        assertEquals("platA", s1Mappings[0].getIssuerId());
        assertEquals("Platform B", s1Mappings[0].getPlatform());

        PlatformMappingDTO[] s2Mappings = getResponseAsObject("/admin/platforms/S2", PlatformMappingDTO[].class);
        assertEquals(2, s2Mappings.length);
        assertTrue(List.of(s2Mappings[0].getIssuerId(), s2Mappings[1].getIssuerId()).contains("platA"));
        assertTrue(List.of(s2Mappings[0].getIssuerId(), s2Mappings[1].getIssuerId()).contains("platB"));

        PlatformMappingDTO[] s3Mappings = getResponseAsObject("/admin/platforms/S3", PlatformMappingDTO[].class);
        assertEquals(1, s3Mappings.length);
        assertEquals("platB", s3Mappings[0].getIssuerId());
    }

    @Test
    void registerIssuer_shouldRejectExistingIssuer_withoutChangingMapping() throws Exception {
        postResponseAsObject("/admin/subject-types", gson.toJson(new SubjectTypeDTO("S1", "Subject 1")), SubjectTypeDTO.class);
        postResponseAsObject("/admin/subject-types", gson.toJson(new SubjectTypeDTO("S2", "Subject 2")), SubjectTypeDTO.class);

        PlatformMappingDTO original = PlatformMappingDTO.builder()
                .subjectTypes(List.of("S1"))
                .platform("Platform A")
                .issuerId("platA")
                .resolutionUrl("https://platform-a.example/dpps/{dppId}")
                .build();
        postResponseAsObject("/admin/platforms/register", gson.toJson(original), PlatformMappingDTO.class);

        PlatformMappingDTO accidentalMigrationViaRegister = PlatformMappingDTO.builder()
                .subjectTypes(List.of("S2"))
                .platform("Platform B")
                .issuerId("platA")
                .resolutionUrl("https://platform-b.example/dpps/{dppId}")
                .build();
        postErrorStatusCode("/admin/platforms/register", gson.toJson(accidentalMigrationViaRegister), HttpStatus.BAD_REQUEST);

        PlatformMappingDTO[] all = getResponseAsObject("/admin/platforms", PlatformMappingDTO[].class);
        assertEquals(1, all.length);
        assertEquals("platA", all[0].getIssuerId());
        assertEquals("Platform A", all[0].getPlatform());
        assertEquals("https://platform-a.example/dpps/{dppId}", all[0].getResolutionUrl());

        PlatformMappingDTO[] s1Mappings = getResponseAsObject("/admin/platforms/S1", PlatformMappingDTO[].class);
        assertEquals(1, s1Mappings.length);
        assertEquals("platA", s1Mappings[0].getIssuerId());

        PlatformMappingDTO[] s2Mappings = getResponseAsObject("/admin/platforms/S2", PlatformMappingDTO[].class);
        assertEquals(0, s2Mappings.length);
    }

    @Test
    void migrateIssuer_shouldRejectUnknownIssuer_withoutCreatingMapping() throws Exception {
        postResponseAsObject("/admin/subject-types", gson.toJson(new SubjectTypeDTO("S1", "Subject 1")), SubjectTypeDTO.class);
        postResponseAsObject("/admin/subject-types", gson.toJson(new SubjectTypeDTO("S2", "Subject 2")), SubjectTypeDTO.class);

        PlatformMappingDTO platformB = PlatformMappingDTO.builder()
                .subjectTypes(List.of("S2"))
                .platform("Platform B")
                .issuerId("platB")
                .resolutionUrl("https://platform-b.example/dpps/{dppId}")
                .build();
        postResponseAsObject("/admin/platforms/register", gson.toJson(platformB), PlatformMappingDTO.class);

        PlatformMigrationRequestDTO accidentalRegistrationViaMigrate = PlatformMigrationRequestDTO.builder()
                .platform("Platform B")
                .newResolutionUrl("https://platform-b.example/dpps/{dppId}")
                .build();
        postErrorStatusCode("/admin/platforms/platA/migrate", gson.toJson(accidentalRegistrationViaMigrate), HttpStatus.BAD_REQUEST);

        PlatformMappingDTO[] all = getResponseAsObject("/admin/platforms", PlatformMappingDTO[].class);
        assertEquals(1, all.length);
        assertEquals("platB", all[0].getIssuerId());

        PlatformMappingDTO[] s1Mappings = getResponseAsObject("/admin/platforms/S1", PlatformMappingDTO[].class);
        assertEquals(0, s1Mappings.length);

        PlatformMappingDTO[] s2Mappings = getResponseAsObject("/admin/platforms/S2", PlatformMappingDTO[].class);
        assertEquals(1, s2Mappings.length);
        assertEquals("platB", s2Mappings[0].getIssuerId());
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
        
        postErrorStatusCode("/admin/platforms/register", gson.toJson(mapping), HttpStatus.BAD_REQUEST);
    }
}
