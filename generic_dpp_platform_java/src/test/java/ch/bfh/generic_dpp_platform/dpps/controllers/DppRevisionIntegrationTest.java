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
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import static org.junit.jupiter.api.Assertions.assertEquals;

public class DppRevisionIntegrationTest extends ControllerTest {

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

    @Test
    public void testRevisionFlow_Success() throws Exception {
        String dppId = ISSUER_ID + "-123";
        
        // 1. Create DPP revision 1
        DppRevisionRequestDTO req1 = createRequest(dppId, 1, Map.of("version", "one"));
        DppRevisionResponseDTO resp1 = postResponseAsObject("/dpps/issue", createGson(false).toJson(req1), DppRevisionResponseDTO.class);
        assertEquals(1, resp1.getVersion());
        assertEquals(Map.of("version", "one"), resp1.getDppPayload());

        // 2. Append revision 2
        DppRevisionRequestDTO req2 = createRequest(dppId, 2, Map.of("version", "two"));
        DppRevisionResponseDTO resp2 = postResponseAsObject("/dpps/" + dppId + "/revise", createGson(false).toJson(req2), DppRevisionResponseDTO.class);
        assertEquals(2, resp2.getVersion());
        assertEquals(Map.of("version", "two"), resp2.getDppPayload());

        // 3. Verify revision 1 is unchanged
        DppRevisionResponseDTO resp1Verify = getResponseAsObject("/dpps/" + dppId + "/1", DppRevisionResponseDTO.class);
        assertEquals(Map.of("version", "one"), resp1Verify.getDppPayload());

        // 4. Append revision 3 without specifying version
        DppRevisionRequestDTO req3 = createRequest(dppId, null, Map.of("version", "three"));
        DppRevisionResponseDTO resp3 = postResponseAsObject("/dpps/" + dppId + "/revise", createGson(false).toJson(req3), DppRevisionResponseDTO.class);
        assertEquals(3, resp3.getVersion());

        // 5. Try appending with a skipped version (5)
        DppRevisionRequestDTO reqSkip = createRequest(dppId, 5, Map.of("version", "skipped"));
        postErrorStatusCode("/dpps/" + dppId + "/revise", createGson(false).toJson(reqSkip), HttpStatus.CONFLICT);

        // 6. Try appending with an old version (2)
        DppRevisionRequestDTO reqOld = createRequest(dppId, 2, Map.of("version", "old"));
        postErrorStatusCode("/dpps/" + dppId + "/revise", createGson(false).toJson(reqOld), HttpStatus.CONFLICT);
    }

    @Test
    public void testConcurrency_Appends() throws Exception {
        String dppId = ISSUER_ID + "-concurrent";
        
        // Create initial revision
        DppRevisionRequestDTO req1 = createRequest(dppId, 1, Map.of("init", "true"));
        postResponseAsObject("/dpps/issue", createGson(false).toJson(req1), DppRevisionResponseDTO.class);

        int threadCount = 5;
        ExecutorService executor = Executors.newFixedThreadPool(threadCount);
        List<CompletableFuture<Integer>> futures = new ArrayList<>();

        for (int i = 0; i < threadCount; i++) {
            final int index = i;
            futures.add(CompletableFuture.supplyAsync(() -> {
                try {
                    // Try to append without specifying version
                    DppRevisionRequestDTO req = createRequest(dppId, null, Map.of("thread", String.valueOf(index)));
                    DppRevisionResponseDTO resp = postResponseAsObject("/dpps/" + dppId + "/revise", createGson(false).toJson(req), DppRevisionResponseDTO.class);
                    return resp.getVersion();
                } catch (Exception e) {
                    return -1;
                }
            }, executor));
        }

        CompletableFuture.allOf(futures.toArray(new CompletableFuture[0])).join();

        List<Integer> results = futures.stream().map(CompletableFuture::join).toList();
        executor.shutdown();

        // All should succeed with different versions if pessimistic lock works
        long successCount = results.stream().filter(v -> v > 1).count();
        assertEquals(threadCount, successCount, "All concurrent requests should have succeeded");
        
        // Verify we have versions 1, 2, 3, 4, 5, 6
        List<Integer> sortedVersions = results.stream().filter(v -> v > 0).sorted().toList();
        for (int i = 0; i < threadCount; i++) {
            assertEquals(i + 2, sortedVersions.get(i));
        }
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
