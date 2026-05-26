package ch.bfh.generic_dpp_platform.dpps.controllers;

import ch.bfh.generic_dpp_platform.ControllerTest;
import ch.bfh.generic_dpp_platform.admin.dtos.SubjectTypeDTO;
import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionRequestDTO;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionResponseDTO;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionSchemaDTO;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchema;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchemaId;
import ch.bfh.generic_dpp_platform.schemas.repositories.DppSchemaRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;

import java.time.Instant;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

public class DppControllerTest extends ControllerTest {

    @Autowired
    private SubjectTypeRepository subjectTypeRepository;

    @Autowired
    private DppSchemaRepository dppSchemaRepository;

    private static final String ISSUER_ID = "issuerA";
    private static final String SUBJECT_TYPE = "Battery";

    @BeforeEach
    public void setupData() throws Exception {
        // Setup Subject Type via REST
        SubjectTypeDTO stDto = SubjectTypeDTO.builder()
                .name(SUBJECT_TYPE)
                .description("Battery subject type")
                .build();
        postResponseAsObject("/admin/subject-types", createGson(false).toJson(stDto), SubjectTypeDTO.class);

        SubjectType st = subjectTypeRepository.findByName(SUBJECT_TYPE).orElseThrow();

        // Setup Schema via Repository (no REST endpoint for this in platform)
        DppSchemaId schemaId = DppSchemaId.builder()
                .subjectTypeName(SUBJECT_TYPE)
                .majorVersion(1)
                .minorVersion(0)
                .build();
        
        DppSchema schema = DppSchema.builder()
                .id(schemaId)
                .subjectType(st)
                .schemaDocument(new ObjectMapper().readTree("{}"))
                .publishedAt(Instant.now())
                .build();
        dppSchemaRepository.save(schema);
    }

    @Test
    public void testCreateDppWithExplicitId_Success() throws Exception {
        String explicitId = ISSUER_ID + "-123";
        DppRevisionRequestDTO request = createRequest(explicitId);

        String json = createGson(false).toJson(request);
        DppRevisionResponseDTO response = sendRequestAndExpectObject(post("/dpps/issue").content(json).contentType("application/json"), DppRevisionResponseDTO.class, HttpStatus.CREATED);

        assertNotNull(response);
        assertEquals(explicitId, response.getDppId());
        assertEquals(1, response.getVersion());
    }

    @Test
    public void testCreateDppWithDuplicateExplicitId_Conflict() throws Exception {
        String explicitId = ISSUER_ID + "-123";
        DppRevisionRequestDTO request = createRequest(explicitId);

        // First issuance
        postResponseAsObject("/dpps/issue", createGson(false).toJson(request), DppRevisionResponseDTO.class);

        // Second issuance with same ID
        postErrorStatusCode("/dpps/issue", createGson(false).toJson(request), HttpStatus.CONFLICT);
    }

    @Test
    public void testCreateDppWithInvalidIssuerPrefix_BadRequest() throws Exception {
        String invalidId = "wrongIssuer-123";
        DppRevisionRequestDTO request = createRequest(invalidId);

        postErrorStatusCode("/dpps/issue", createGson(false).toJson(request), HttpStatus.BAD_REQUEST);
    }

    @Test
    public void testCreateDppWithoutExplicitId_GeneratesId() throws Exception {
        DppRevisionRequestDTO request = createRequest(null);

        DppRevisionResponseDTO response = postResponseAsObject("/dpps/issue", createGson(false).toJson(request), DppRevisionResponseDTO.class);

        assertNotNull(response);
        assertTrue(response.getDppId().startsWith(ISSUER_ID));
        assertEquals(1, response.getVersion());
    }

    private DppRevisionRequestDTO createRequest(String dppId) {
        return DppRevisionRequestDTO.builder()
                .dppId(dppId)
                .version(1)
                .schemaVersion(DppRevisionSchemaDTO.builder()
                        .subjectType(SUBJECT_TYPE)
                        .majorVersion(1)
                        .minorVersion(0)
                        .build())
                .dppPayload(Map.of("test", "data"))
                .build();
    }
}
