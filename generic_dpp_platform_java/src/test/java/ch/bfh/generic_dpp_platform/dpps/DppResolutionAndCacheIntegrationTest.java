package ch.bfh.generic_dpp_platform.dpps;

import ch.bfh.generic_dpp_platform.ControllerTest;
import ch.bfh.generic_dpp_platform.admin.dtos.SubjectTypeDTO;
import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionRequestDTO;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionSchemaDTO;
import ch.bfh.generic_dpp_platform.dpps.models.ReferencedDppRevision;
import ch.bfh.generic_dpp_platform.dpps.models.ReferencedDppRevisionId;
import ch.bfh.generic_dpp_platform.dpps.repositories.ReferencedDppRevisionRepository;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchema;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchemaId;
import ch.bfh.generic_dpp_platform.schemas.repositories.DppSchemaRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

import java.time.Instant;
import java.util.Map;

import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

public class DppResolutionAndCacheIntegrationTest extends ControllerTest {

    @Autowired
    private RestTemplate restTemplate;

    @Autowired
    @Qualifier("noRedirectRestTemplate")
    private RestTemplate noRedirectRestTemplate;

    private MockRestServiceServer mockServer;
    private MockRestServiceServer mockNoRedirectServer;

    @Autowired
    private ReferencedDppRevisionRepository cacheRepository;

    @Autowired
    private SubjectTypeRepository subjectTypeRepository;

    @Autowired
    private DppSchemaRepository dppSchemaRepository;

    private static final String RESOLVER_BASE_URL = "http://localhost:8080";
    private static final String SUBJECT_TYPE = "battery";

    @BeforeEach
    public void setupData() throws Exception {
        mockServer = MockRestServiceServer.createServer(restTemplate);
        mockNoRedirectServer = MockRestServiceServer.createServer(noRedirectRestTemplate);

        // Setup Subject Type via REST
        SubjectTypeDTO stDto = SubjectTypeDTO.builder()
                .name(SUBJECT_TYPE)
                .description("Battery subject type")
                .build();
        postResponseAsObject("/admin/subject-types", createGson(false).toJson(stDto), SubjectTypeDTO.class);

        SubjectType st = subjectTypeRepository.findByName(SUBJECT_TYPE).orElseThrow();

        // Setup Schema via Repository
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

    protected String toJson(Object obj) {
        return createGson(false).toJson(obj);
    }

    @Test
    void testFailedResolutionReturns424() throws Exception {
        mockNoRedirectServer.expect(requestTo(RESOLVER_BASE_URL + "/battery/issuerB-001/1"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withStatus(HttpStatus.NOT_FOUND));

        DppRevisionRequestDTO request = new DppRevisionRequestDTO();
        request.setDppId("issuerA-001");
        request.setSchemaVersion(new DppRevisionSchemaDTO(SUBJECT_TYPE, 1, 0));
        request.setDppPayload(Map.of("$ref", "battery/issuerB-001", "version", 1));

        mvc.perform(post("/dpps/issue")
                .contentType("application/json")
                .content(toJson(request)))
                .andExpect(status().isFailedDependency());
        
        mockNoRedirectServer.verify();
    }

    @Test
    void testCacheHitAvoidsResolverCall() throws Exception {
        // Pre-populate cache with CORRECT hash
        Map<String, Object> doc = Map.of("data", "cached");
        byte[] hash = ch.bfh.generic_dpp_platform.dpps.utils.DppUtil.hashDocument(doc);
        
        ReferencedDppRevision cached = ReferencedDppRevision.builder()
                .id(new ReferencedDppRevisionId("issuerB-001", 1))
                .subjectType(SUBJECT_TYPE)
                .schemaSubjectType(SUBJECT_TYPE)
                .schemaMajorVersion(1)
                .schemaMinorVersion(0)
                .dppDocument(doc)
                .hashedDocument(hash)
                .fetchedAt(Instant.now())
                .build();
        cacheRepository.save(cached);

        DppRevisionRequestDTO request = new DppRevisionRequestDTO();
        request.setDppId("issuerA-001");
        request.setSchemaVersion(new DppRevisionSchemaDTO(SUBJECT_TYPE, 1, 0));
        request.setDppPayload(Map.of("$ref", "battery/issuerB-001", "version", 1));

        mvc.perform(post("/dpps/issue")
                .contentType("application/json")
                .content(toJson(request)))
                .andExpect(status().isCreated());

        // No expectations on mockServer means no calls were made
        mockServer.verify();
        mockNoRedirectServer.verify();
    }
}
