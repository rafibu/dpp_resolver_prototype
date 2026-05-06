package ch.bfh.generic_dpp_platform.schemas.connectors;

import ch.bfh.generic_dpp_platform.TestDatabaseCleaner;
import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionResponseDTO;
import ch.bfh.generic_dpp_platform.dpps.exceptions.DppReferenceResolutionException;
import ch.bfh.generic_dpp_platform.schemas.dtos.DppSchemaDTO;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchema;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchemaId;
import ch.bfh.generic_dpp_platform.schemas.repositories.DppSchemaRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

import java.net.URI;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

@SpringBootTest
@ActiveProfiles("test")
class ResolverConnectorTest {

    @Autowired
    private RestTemplate restTemplate;

    @Autowired
    @Qualifier("noRedirectRestTemplate")
    private RestTemplate noRedirectRestTemplate;

    private MockRestServiceServer mockServer;
    private MockRestServiceServer mockNoRedirectServer;

    @Autowired
    private SubjectTypeRepository subjectTypeRepository;

    @Autowired
    private DppSchemaRepository dppSchemaRepository;

    @Autowired
    private TestDatabaseCleaner databaseCleaner;

    @Autowired
    private ResolverConnector resolverConnector;

    private static final String RESOLVER_BASE_URL = "http://localhost:8080";
    private final ObjectMapper mapper = new ObjectMapper().findAndRegisterModules();

    @BeforeEach
    void setUp() {
        databaseCleaner.clean();
        mockServer = MockRestServiceServer.createServer(restTemplate);
        mockNoRedirectServer = MockRestServiceServer.createServer(noRedirectRestTemplate);

        SubjectType st = SubjectType.builder()
                .name("TestType")
                .build();
        subjectTypeRepository.save(st);
    }

    @Test
    void syncSchema_Success() throws Exception {
        String typeName = "TestType";
        DppSchemaDTO s1 = DppSchemaDTO.builder()
                .majorVersion(1).minorVersion(0).publishedAt(Instant.now()).schemaDocument(Map.of("type", "object"))
                .build();
        DppSchemaDTO[] remoteSchemas = {s1};

        mockServer.expect(requestTo(RESOLVER_BASE_URL + "/schemas/" + typeName))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(mapper.writeValueAsString(remoteSchemas), MediaType.APPLICATION_JSON));

        resolverConnector.syncSchema(typeName);

        assertTrue(dppSchemaRepository.existsById(new DppSchemaId(0, 1, typeName)));
        mockServer.verify();
    }

    @Test
    void resolveDppRevisionUrl_FollowsRedirect() throws Exception {
        String subjectType = "battery";
        String dppId = "item-001";
        int version = 1;
        String targetUrl = "https://platform-b.com/dpps/item-001/1";

        mockNoRedirectServer.expect(requestTo(RESOLVER_BASE_URL + "/battery/item-001/1"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withStatus(HttpStatus.FOUND)
                        .header(HttpHeaders.LOCATION, targetUrl));

        URI resolvedUri = resolverConnector.resolveDppRevisionUrl(subjectType, dppId, version);

        assertEquals(targetUrl, resolvedUri.toString());
        mockNoRedirectServer.verify();
    }

    @Test
    void resolveDppRevision_FetchesFromResolvedUrl() throws Exception {
        String subjectType = "battery";
        String dppId = "item-001";
        int version = 1;
        String targetUrl = "https://platform-b.com/dpps/item-001/1";

        // 1. Resolve URL (Redirect)
        mockNoRedirectServer.expect(requestTo(RESOLVER_BASE_URL + "/battery/item-001/1"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withStatus(HttpStatus.FOUND)
                        .header(HttpHeaders.LOCATION, targetUrl));

        // 2. Fetch from resolved URL
        DppRevisionResponseDTO mockResponse = new DppRevisionResponseDTO();
        mockResponse.setDppId(dppId);
        mockResponse.setVersion(version);
        mockResponse.setDppPayload(Map.of("key", "value"));

        mockServer.expect(requestTo(targetUrl))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(mapper.writeValueAsString(mockResponse), MediaType.APPLICATION_JSON));

        DppRevisionResponseDTO result = resolverConnector.resolveDppRevision(subjectType, dppId, version);

        assertNotNull(result);
        assertEquals(dppId, result.getDppId());
        mockNoRedirectServer.verify();
        mockServer.verify();
    }

    @Test
    void resolveDppRevisionUrl_ThrowsExceptionOnNotFound() {
        mockNoRedirectServer.expect(requestTo(RESOLVER_BASE_URL + "/battery/item-999/1"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withStatus(HttpStatus.NOT_FOUND));

        assertThrows(DppReferenceResolutionException.class, 
                () -> resolverConnector.resolveDppRevisionUrl("battery", "item-999", 1));
        
        mockNoRedirectServer.verify();
    }
}
