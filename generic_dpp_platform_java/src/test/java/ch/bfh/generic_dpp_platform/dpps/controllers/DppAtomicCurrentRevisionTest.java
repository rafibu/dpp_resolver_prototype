package ch.bfh.generic_dpp_platform.dpps.controllers;

import ch.bfh.generic_dpp_platform.ControllerTest;
import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import ch.bfh.generic_dpp_platform.admin.services.PlatformConfigService;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppDetailDTO;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionRequestDTO;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionResponseDTO;
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
import org.springframework.test.context.TestPropertySource;

import java.time.Instant;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

@TestPropertySource(properties = "platform.issuer-id=issuerB")
public class DppAtomicCurrentRevisionTest extends ControllerTest {

    @Autowired
    private LogicalDppRepository logicalDppRepository;

    @Autowired
    private DppRevisionRepository dppRevisionRepository;

    @Autowired
    private SubjectTypeRepository subjectTypeRepository;

    @Autowired
    private DppSchemaRepository dppSchemaRepository;

    @Autowired
    private PlatformConfigService platformConfigService;

    private static final String ISSUER_ID = "issuerB";
    private static final String SUBJECT_TYPE = "Component";

    @BeforeEach
    public void setupData() throws Exception {
        cleanup();

        SubjectType st = SubjectType.builder()
                .name(SUBJECT_TYPE)
                .description("Component subject type")
                .build();
        subjectTypeRepository.save(st);

        DppSchemaId schemaId = new DppSchemaId();
        schemaId.setSubjectTypeName(SUBJECT_TYPE);
        schemaId.setMajorVersion(1);
        schemaId.setMinorVersion(0);

        DppSchema schema = DppSchema.builder()
                .id(schemaId)
                .subjectType(st)
                .schemaDocument(new ObjectMapper().readTree("{}"))
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
    public void testCurrentRevisionReturnsHighestVersion() throws Exception {
        String dppId = ISSUER_ID + "-atomic-1";

        postResponseAsObject("/dpps", createGson(false).toJson(createRequest(dppId, 1, Map.of("v", 1))), DppRevisionResponseDTO.class);
        postResponseAsObject("/dpps/" + dppId, createGson(false).toJson(createRequest(dppId, 2, Map.of("v", 2))), DppRevisionResponseDTO.class);
        postResponseAsObject("/dpps/" + dppId, createGson(false).toJson(createRequest(dppId, 3, Map.of("v", 3))), DppRevisionResponseDTO.class);

        // GET /dpps/:id now returns DppDetailDTO with all revisions
        DppDetailDTO current = getResponseAsObject("/dpps/" + dppId, DppDetailDTO.class);
        assertEquals(3, current.getRevisions().size());
        assertEquals(3, current.getRevisions().get(current.getRevisions().size() - 1).getVersion());

        postResponseAsObject("/dpps/" + dppId, createGson(false).toJson(createRequest(dppId, 4, Map.of("v", 4))), DppRevisionResponseDTO.class);
        current = getResponseAsObject("/dpps/" + dppId, DppDetailDTO.class);
        assertEquals(4, current.getRevisions().get(current.getRevisions().size() - 1).getVersion());

        // GET /dpps/:id/:version still returns single revision
        DppRevisionResponseDTO v2 = getResponseAsObject("/dpps/" + dppId + "/2", DppRevisionResponseDTO.class);
        assertEquals(2, v2.getVersion());
    }

    @Test
    public void testGetNonExistentDppReturns404() throws Exception {
        getErrorStatusCode("/dpps/non-existent", HttpStatus.NOT_FOUND);
    }

    private DppRevisionRequestDTO createRequest(String dppId, Integer version, Map<String, Object> payload) {
        return DppRevisionRequestDTO.builder()
                .dppId(dppId)
                .version(version)
                .schemaVersion(DppRevisionSchemaDTO.builder()
                        .subjectType(SUBJECT_TYPE)
                        .majorVersion(1)
                        .minorVersion(0)
                        .build())
                .dppPayload(payload)
                .build();
    }
}
