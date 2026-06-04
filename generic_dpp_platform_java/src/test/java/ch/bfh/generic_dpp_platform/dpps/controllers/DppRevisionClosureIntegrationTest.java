package ch.bfh.generic_dpp_platform.dpps.controllers;

import ch.bfh.generic_dpp_platform.ControllerTest;
import ch.bfh.generic_dpp_platform.admin.dtos.ApiError;
import ch.bfh.generic_dpp_platform.admin.dtos.SubjectTypeDTO;
import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionClosureResponseDTO;
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
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

public class DppRevisionClosureIntegrationTest extends ControllerTest {

    @Autowired
    private SubjectTypeRepository subjectTypeRepository;

    @Autowired
    private DppSchemaRepository dppSchemaRepository;

    private static final String ISSUER_ID = "issuerA";
    private static final String SUBJECT_TYPE = "Battery";

    @BeforeEach
    public void setupData() throws Exception {
        SubjectTypeDTO stDto = SubjectTypeDTO.builder()
                .name(SUBJECT_TYPE)
                .description("Battery subject type")
                .build();
        postResponseAsObject("/admin/subject-types", createGson(false).toJson(stDto), SubjectTypeDTO.class);

        SubjectType st = subjectTypeRepository.findByName(SUBJECT_TYPE).orElseThrow();

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
    public void testClosureMaxDepthOneResolvesOnlyDirectHardReferences() throws Exception {
        ChainIds chain = createChain();

        DppRevisionClosureResponseDTO response = getResponseAsObject(
                "/dpps/" + chain.root() + "/1/closure?maxDepth=1",
                DppRevisionClosureResponseDTO.class
        );

        assertEquals(chain.root(), response.getRootRevision().getDppId());
        assertEquals(List.of(chain.middle()), resolvedIds(response));
    }

    @Test
    public void testClosureMaxDepthTwoResolvesTransitiveHardReferences() throws Exception {
        ChainIds chain = createChain();

        DppRevisionClosureResponseDTO response = getResponseAsObject(
                "/dpps/" + chain.root() + "/1/closure?maxDepth=2",
                DppRevisionClosureResponseDTO.class
        );

        assertEquals(chain.root(), response.getRootRevision().getDppId());
        assertEquals(List.of(chain.middle(), chain.leaf()), resolvedIds(response));
    }

    @Test
    public void testClosureSkipsDuplicateHardReferences() throws Exception {
        String root = ISSUER_ID + "-duplicate-root";
        String dependency = ISSUER_ID + "-duplicate-dependency";

        issueDpp(dependency, Map.of("name", "dependency"));
        issueDpp(root, Map.of(
                "dependencies",
                List.of(
                        hardRef(dependency),
                        hardRef(dependency)
                )
        ));

        DppRevisionClosureResponseDTO response = getResponseAsObject(
                "/dpps/" + root + "/1/closure?maxDepth=1",
                DppRevisionClosureResponseDTO.class
        );

        assertEquals(List.of(dependency), resolvedIds(response));
    }

    @Test
    public void testClosureRejectsInvalidMaxDepth() throws Exception {
        ApiError error = sendRequestAndExpectObject(
                get("/dpps/" + ISSUER_ID + "-missing/1/closure?maxDepth=0"),
                ApiError.class,
                HttpStatus.BAD_REQUEST
        );

        assertEquals("Invalid Argument", error.getError());
        assertTrue(error.getMessage().contains("maxDepth"));
    }

    private ChainIds createChain() throws Exception {
        String root = ISSUER_ID + "-chain-a";
        String middle = ISSUER_ID + "-chain-b";
        String leaf = ISSUER_ID + "-chain-c";

        issueDpp(leaf, Map.of("name", "leaf"));
        issueDpp(middle, Map.of("dependency", hardRef(leaf)));
        issueDpp(root, Map.of("dependency", hardRef(middle)));

        return new ChainIds(root, middle, leaf);
    }

    private DppRevisionResponseDTO issueDpp(String dppId, Map<String, Object> payload) throws Exception {
        DppRevisionRequestDTO request = DppRevisionRequestDTO.builder()
                .dppId(dppId)
                .version(1)
                .schemaVersion(DppRevisionSchemaDTO.builder()
                        .subjectType(SUBJECT_TYPE)
                        .majorVersion(1)
                        .minorVersion(0)
                        .build())
                .dppPayload(payload)
                .build();

        return postResponseAsObject("/dpps/issue", createGson(false).toJson(request), DppRevisionResponseDTO.class);
    }

    private Map<String, Object> hardRef(String dppId) {
        return Map.of("$ref", SUBJECT_TYPE + "/" + dppId, "version", 1);
    }

    private List<String> resolvedIds(DppRevisionClosureResponseDTO response) {
        return response.getResolvedRevisions().stream()
                .map(DppRevisionResponseDTO::getDppId)
                .toList();
    }

    private record ChainIds(String root, String middle, String leaf) {
    }
}
