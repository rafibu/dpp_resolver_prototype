package ch.bfh.generic_dpp_platform.dpps;

import ch.bfh.generic_dpp_platform.ControllerTest;
import ch.bfh.generic_dpp_platform.admin.dtos.PlatformConfigDTO;
import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import ch.bfh.generic_dpp_platform.admin.services.PlatformConfigService;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionRequestDTO;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionResponseDTO;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionSchemaDTO;
import ch.bfh.generic_dpp_platform.dpps.repositories.DppRevisionRepository;
import ch.bfh.generic_dpp_platform.dpps.repositories.LogicalDppRepository;
import ch.bfh.generic_dpp_platform.schemas.connectors.ResolverConnector;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchema;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchemaId;
import ch.bfh.generic_dpp_platform.schemas.repositories.DppSchemaRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.http.HttpStatus;

import java.time.Instant;
import java.util.Map;

import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

public class DppCycleDetectionIntegrationTest extends ControllerTest {

    @MockitoBean
    private ResolverConnector resolverConnector;

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

    private static final String ISSUER_ID = "issuerA";
    private static final String SUBJECT_TYPE = "battery";

    @BeforeEach
    public void setupData() throws Exception {
        cleanup();

        // Setup Subject Type
        SubjectType st = SubjectType.builder()
                .name(SUBJECT_TYPE)
                .description("Battery subject type")
                .build();
        subjectTypeRepository.save(st);

        // Setup Schema
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

    @AfterEach
    public void cleanup() {
        dppRevisionRepository.deleteAll();
        logicalDppRepository.deleteAll();
        dppSchemaRepository.deleteAll();
        subjectTypeRepository.deleteAll();
    }

    protected String toJson(Object obj) {
        return createGson(false).toJson(obj);
    }

    @Test
    void testDirectCycleIsRejected() throws Exception {
        // Mock Resolver to return a revision that depends back on the candidate
        // Candidate: battery/issuerA-001 (local)
        // Depends on: battery/issuerB-001 (external)
        // issuerB-001 depends on: battery/issuerA-001/1
        
        String localDppId = "issuerA-001";
        String validHash = "0000000000000000000000000000000000000000000000000000000000000000";
        
        DppRevisionResponseDTO externalRevision = DppRevisionResponseDTO.builder()
                .dppId("issuerB-001")
                .version(1)
                .schemaVersion(new DppRevisionSchemaDTO("battery", 1, 0))
                .dppPayload(Map.of("$ref", "battery/issuerA-001/1"))
                .payloadHash(validHash)
                .build();
        
        when(resolverConnector.resolveDppRevision(eq("battery"), eq("issuerB-001"), eq(1)))
                .thenReturn(externalRevision);

        DppRevisionRequestDTO request = new DppRevisionRequestDTO();
        request.setDppId(localDppId);
        request.setVersion(1);
        request.setSchemaVersion(new DppRevisionSchemaDTO("battery", 1, 0));
        request.setDppPayload(Map.of("name", "My Battery", "$ref", "battery/issuerB-001", "version", 1));

        mvc.perform(post("/dpps")
                .contentType("application/json")
                .content(toJson(request)))
                .andDo(print())
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error").value("Cycle Detected"))
                .andExpect(jsonPath("$.details").isArray());
    }

    @Test
    void testTransitiveCycleIsRejected() throws Exception {
        // A -> B -> C -> A
        String validHash = "0000000000000000000000000000000000000000000000000000000000000000";
        
        DppRevisionResponseDTO b = DppRevisionResponseDTO.builder()
                .dppId("issuerB-001").version(1)
                .schemaVersion(new DppRevisionSchemaDTO("battery", 1, 0))
                .dppPayload(Map.of("$ref", "battery/issuerC-001", "version", 1))
                .payloadHash(validHash).build();
        
        DppRevisionResponseDTO c = DppRevisionResponseDTO.builder()
                .dppId("issuerC-001").version(1)
                .schemaVersion(new DppRevisionSchemaDTO("battery", 1, 0))
                .dppPayload(Map.of("$ref", "battery/issuerA-001/1"))
                .payloadHash(validHash).build();

        when(resolverConnector.resolveDppRevision(eq("battery"), eq("issuerB-001"), anyInt())).thenReturn(b);
        when(resolverConnector.resolveDppRevision(eq("battery"), eq("issuerC-001"), anyInt())).thenReturn(c);

        DppRevisionRequestDTO request = new DppRevisionRequestDTO();
        request.setDppId("issuerA-001");
        request.setSchemaVersion(new DppRevisionSchemaDTO("battery", 1, 0));
        request.setDppPayload(Map.of("$ref", "battery/issuerB-001", "version", 1));

        mvc.perform(post("/dpps")
                .contentType("application/json")
                .content(toJson(request)))
                .andDo(print())
                .andExpect(status().isConflict());
    }

    @Test
    void testSoftReferencesDoNotTriggerCycle() throws Exception {
        // A -> B (soft) -> A (hard)
        // Should NOT be a cycle because soft references don't participate.
        
        DppRevisionResponseDTO b = DppRevisionResponseDTO.builder()
                .dppId("issuerB-001").version(1)
                .schemaVersion(new DppRevisionSchemaDTO("battery", 1, 0))
                .dppPayload(Map.of("$ref", "battery/issuerA-001/1"))
                .payloadHash("hashB").build();

        when(resolverConnector.resolveDppRevision(anyString(), anyString(), anyInt())).thenReturn(b);

        DppRevisionRequestDTO request = new DppRevisionRequestDTO();
        request.setDppId("issuerA-001");
        request.setSchemaVersion(new DppRevisionSchemaDTO("battery", 1, 0));
        request.setDppPayload(Map.of("$ref", "battery/issuerB-001")); // SOFT reference

        mvc.perform(post("/dpps")
                .contentType("application/json")
                .content(toJson(request)))
                .andExpect(status().isCreated());
    }

    @Test
    void testCycleDeeperThan3RoundsIsNotDetected() throws Exception {
        // A -> B -> C -> D -> E -> A
        // Round 1 (edges from A): A -> B
        // Round 2 (edges from B): B -> C
        // Round 3 (edges from C): C -> D
        // Round 4 (edges from D): D -> E (Not traversed because we stop after round 3)
        // Round 5 (edges from E): E -> A
        
        String validHash = "0000000000000000000000000000000000000000000000000000000000000000";
        
        DppRevisionResponseDTO b = DppRevisionResponseDTO.builder()
                .dppId("issuerB-001").version(1)
                .schemaVersion(new DppRevisionSchemaDTO("battery", 1, 0))
                .dppPayload(Map.of("$ref", "battery/issuerC-001", "version", 1))
                .payloadHash(validHash).build();
        
        DppRevisionResponseDTO c = DppRevisionResponseDTO.builder()
                .dppId("issuerC-001").version(1)
                .schemaVersion(new DppRevisionSchemaDTO("battery", 1, 0))
                .dppPayload(Map.of("$ref", "battery/issuerD-001", "version", 1))
                .payloadHash(validHash).build();

        DppRevisionResponseDTO d = DppRevisionResponseDTO.builder()
                .dppId("issuerD-001").version(1)
                .schemaVersion(new DppRevisionSchemaDTO("battery", 1, 0))
                .dppPayload(Map.of("$ref", "battery/issuerE-001", "version", 1))
                .payloadHash(validHash).build();

        DppRevisionResponseDTO e = DppRevisionResponseDTO.builder()
                .dppId("issuerE-001").version(1)
                .schemaVersion(new DppRevisionSchemaDTO("battery", 1, 0))
                .dppPayload(Map.of("$ref", "battery/issuerA-001/1"))
                .payloadHash(validHash).build();

        when(resolverConnector.resolveDppRevision(eq("battery"), eq("issuerB-001"), anyInt())).thenReturn(b);
        when(resolverConnector.resolveDppRevision(eq("battery"), eq("issuerC-001"), anyInt())).thenReturn(c);
        when(resolverConnector.resolveDppRevision(eq("battery"), eq("issuerD-001"), anyInt())).thenReturn(d);
        when(resolverConnector.resolveDppRevision(eq("battery"), eq("issuerE-001"), anyInt())).thenReturn(e);

        DppRevisionRequestDTO request = new DppRevisionRequestDTO();
        request.setDppId("issuerA-001");
        request.setSchemaVersion(new DppRevisionSchemaDTO("battery", 1, 0));
        request.setDppPayload(Map.of("$ref", "battery/issuerB-001", "version", 1));

        mvc.perform(post("/dpps")
                .contentType("application/json")
                .content(toJson(request)))
                .andExpect(status().isCreated());
    }
}
