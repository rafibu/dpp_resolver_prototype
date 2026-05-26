package ch.bfh.generic_dpp_platform.dpps.controllers;

import ch.bfh.generic_dpp_platform.ControllerTest;
import ch.bfh.generic_dpp_platform.admin.dtos.ApiError;
import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionRequestDTO;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionSchemaDTO;
import ch.bfh.generic_dpp_platform.dpps.repositories.DppRevisionRepository;
import ch.bfh.generic_dpp_platform.dpps.repositories.LogicalDppRepository;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchema;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchemaId;
import ch.bfh.generic_dpp_platform.schemas.repositories.DppSchemaRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;

import java.time.Instant;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

public class DppErrorHandlingIntegrationTest extends ControllerTest {

    @Autowired
    private LogicalDppRepository logicalDppRepository;

    @Autowired
    private DppRevisionRepository dppRevisionRepository;

    @Autowired
    private SubjectTypeRepository subjectTypeRepository;

    @Autowired
    private DppSchemaRepository dppSchemaRepository;

    private static final String ISSUER_ID = "issuerA";
    private static final String SUBJECT_TYPE = "Battery";

    @BeforeEach
    public void setupData() throws Exception {
        cleanup();

        // Setup Subject Type
        SubjectType st = SubjectType.builder()
                .name(SUBJECT_TYPE)
                .description("Battery subject type")
                .build();
        subjectTypeRepository.save(st);

        // Setup Schema with some requirements
        DppSchemaId schemaId = DppSchemaId.builder()
                .subjectTypeName(SUBJECT_TYPE)
                .majorVersion(1)
                .minorVersion(0)
                .build();
        
        String schemaJson = "{\"type\": \"object\", \"properties\": {\"serialNumber\": {\"type\": \"string\"}, \"capacity\": {\"type\": \"number\"}}, \"required\": [\"serialNumber\"]}";
        
        DppSchema schema = DppSchema.builder()
                .id(schemaId)
                .subjectType(st)
                .schemaDocument(new ObjectMapper().readTree(schemaJson))
                .publishedAt(Instant.now())
                .build();
        dppSchemaRepository.save(schema);
    }

    @AfterEach
    public void cleanup() {
        dppRevisionRepository.deleteAll();
        logicalDppRepository.deleteAll();
        dppSchemaRepository.deleteAll();
        subjectTypeRepository.deleteAll();
    }

    @Test
    public void testSchemaValidationFailure_ReturnsStructuredError() throws Exception {
        DppRevisionRequestDTO request = DppRevisionRequestDTO.builder()
                .schemaVersion(DppRevisionSchemaDTO.builder()
                        .subjectType(SUBJECT_TYPE)
                        .majorVersion(1)
                        .minorVersion(0)
                        .build())
                .dppPayload(Map.of("capacity", 100)) // Missing serialNumber
                .build();

        String json = createGson(false).toJson(request);
        ApiError error = sendRequestAndExpectObject(post("/dpps/issue").content(json).contentType("application/json"), ApiError.class, HttpStatus.BAD_REQUEST);

        assertNotNull(error);
        assertEquals("Schema Validation Failed", error.getError());
        assertNotNull(error.getDetails());
        assertTrue(error.getDetails().stream().anyMatch(d -> d.contains("serialNumber")),
                "Expected error about serialNumber, but got: " + error.getDetails());
        assertNotNull(error.getTimestamp());
        assertEquals("/dpps/issue", error.getPath());
    }

    @Test
    public void testInvalidSchemaVersion_ReturnsStructuredError() throws Exception {
        DppRevisionRequestDTO request = DppRevisionRequestDTO.builder()
                .schemaVersion(DppRevisionSchemaDTO.builder()
                        .subjectType(SUBJECT_TYPE)
                        .majorVersion(99)
                        .minorVersion(0)
                        .build())
                .dppPayload(Map.of("serialNumber", "123"))
                .build();

        String json = createGson(false).toJson(request);
        ApiError error = sendRequestAndExpectObject(post("/dpps/issue").content(json).contentType("application/json"), ApiError.class, HttpStatus.BAD_REQUEST);

        assertNotNull(error);
        assertEquals("Invalid Argument", error.getError());
        assertEquals("Schema version not found", error.getMessage());
    }

    @Test
    public void testNonExistentDpp_ReturnsStructuredError() throws Exception {
        ApiError error = sendRequestAndExpectObject(get("/dpps/non-existent-id"), ApiError.class, HttpStatus.NOT_FOUND);

        assertNotNull(error);
        assertEquals("Not Found", error.getError());
        assertTrue(error.getMessage().contains("DPP not found"));
    }

    @Test
    public void testDuplicateDppId_ReturnsStructuredError() throws Exception {
        String explicitId = ISSUER_ID + "-duplicate";
        DppRevisionRequestDTO request = DppRevisionRequestDTO.builder()
                .dppId(explicitId)
                .schemaVersion(DppRevisionSchemaDTO.builder()
                        .subjectType(SUBJECT_TYPE)
                        .majorVersion(1)
                        .minorVersion(0)
                        .build())
                .dppPayload(Map.of("serialNumber", "SN123"))
                .build();

        String json = createGson(false).toJson(request);
        // First creation
        sendRequestAndExpectObject(post("/dpps/issue").content(json).contentType("application/json"), Map.class, HttpStatus.CREATED);

        // Duplicate creation
        ApiError error = sendRequestAndExpectObject(post("/dpps/issue").content(json).contentType("application/json"), ApiError.class, HttpStatus.CONFLICT);

        assertNotNull(error);
        assertEquals("DPP Already Exists", error.getError());
        assertTrue(error.getMessage().contains("DPP already exists"));
    }
}
