package ch.bfh.generic_dpp_platform.dpps;

import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionRequestDTO;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionResponseDTO;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionSchemaDTO;
import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import ch.bfh.generic_dpp_platform.dpps.models.DppRevision;
import ch.bfh.generic_dpp_platform.dpps.models.DppRevisionId;
import ch.bfh.generic_dpp_platform.dpps.models.LogicalDpp;
import ch.bfh.generic_dpp_platform.dpps.repositories.DppRevisionRepository;
import ch.bfh.generic_dpp_platform.dpps.repositories.LogicalDppRepository;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchema;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchemaId;
import ch.bfh.generic_dpp_platform.schemas.repositories.DppSchemaRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@ActiveProfiles("test")
@Transactional
public class HashIntegrityTest {

    @Autowired
    private DppRevisionRepository dppRevisionRepository;

    @Autowired
    private LogicalDppRepository logicalDppRepository;

    @Autowired
    private SubjectTypeRepository subjectTypeRepository;

    @Autowired
    private DppSchemaRepository dppSchemaRepository;

    @Autowired
    private ch.bfh.generic_dpp_platform.dpps.services.DppRevisionService dppRevisionService;

    private LogicalDpp testDpp;
    private DppSchema testSchema;

    @BeforeEach
    void setUp() throws Exception {
        SubjectType st = SubjectType.builder()
                .name("TestType")
                .description("Test Description")
                .build();
        subjectTypeRepository.save(st);

        testDpp = new LogicalDpp();
        testDpp.setDppId("issuerA-123");
        testDpp.setSubjectType(st);
        logicalDppRepository.save(testDpp);

        DppSchemaId schemaId = DppSchemaId.builder()
                .subjectTypeName("TestType")
                .majorVersion(1)
                .minorVersion(0)
                .build();

        testSchema = DppSchema.builder()
                .id(schemaId)
                .subjectType(st)
                .schemaDocument(new ObjectMapper().readTree("{}"))
                .publishedAt(Instant.now())
                .build();
        dppSchemaRepository.save(testSchema);
    }

    @Test
    void testPersistRevisionWithValidHash_ShouldSucceed() {
        DppRevision revision = new DppRevision();
        revision.setId(new DppRevisionId(1, testDpp.getDppId()));
        revision.setDpp(testDpp);
        revision.setDppSchema(testSchema);
        Map<String, Object> doc = Map.of("data", "value");
        revision.setDppDocument(doc);
        revision.setCreatedAt(Instant.now());
        
        byte[] correctHash = ch.bfh.generic_dpp_platform.dpps.utils.DppUtil.hashDocument(doc);
        revision.setHashedDocument(correctHash);

        assertDoesNotThrow(() -> {
            dppRevisionRepository.saveAndFlush(revision);
        });
    }

    @Test
    void testPersistRevisionWithInvalidHash_ShouldFail() {
        DppRevision revision = new DppRevision();
        revision.setId(new DppRevisionId(1, testDpp.getDppId()));
        revision.setDpp(testDpp);
        revision.setDppSchema(testSchema);
        revision.setDppDocument(Map.of("data", "value"));
        revision.setCreatedAt(Instant.now());
        
        // Setting an obviously wrong hash
        revision.setHashedDocument(new byte[]{1, 2, 3});

        Exception ex = assertThrows(Exception.class, () -> dppRevisionRepository.saveAndFlush(revision));
        assertTrue(ex.getMessage().contains("integrity violation"), "Exception message should contain 'integrity violation'");
    }

    @Test
    void testPersistRevisionWithMissingHash_ShouldAutoCompute() {
        DppRevision revision = new DppRevision();
        revision.setId(new DppRevisionId(1, testDpp.getDppId()));
        revision.setDpp(testDpp);
        revision.setDppSchema(testSchema);
        Map<String, Object> doc = Map.of("data", "value");
        revision.setDppDocument(doc);
        revision.setCreatedAt(Instant.now());
        
        // Hash is null
        revision.setHashedDocument(null);

        DppRevision saved = dppRevisionRepository.saveAndFlush(revision);
        
        assertNotNull(saved.getHashedDocument(), "Hash should have been auto-computed");
        byte[] expectedHash = ch.bfh.generic_dpp_platform.dpps.utils.DppUtil.hashDocument(doc);
        assertArrayEquals(expectedHash, saved.getHashedDocument());
    }

    @Test
    void testUpdateRevisionWithInvalidHash_ShouldFail() {
        // 1. Save valid revision
        DppRevision revision = new DppRevision();
        revision.setId(new DppRevisionId(1, testDpp.getDppId()));
        revision.setDpp(testDpp);
        revision.setDppSchema(testSchema);
        Map<String, Object> doc = Map.of("data", "value");
        revision.setDppDocument(doc);
        revision.setCreatedAt(Instant.now());
        revision = dppRevisionRepository.saveAndFlush(revision);

        // 2. Modify payload but keep old hash (stale hash)
        revision.setDppDocument(Map.of("data", "changed"));
        // hashedDocument is still the hash of {"data": "value"}

        DppRevision finalRevision = revision;
        Exception ex = assertThrows(Exception.class, () -> dppRevisionRepository.saveAndFlush(finalRevision));
        // @PreUpdate rejectUpdate() fires: revisions are immutable, so any update is rejected.
        assertTrue(ex.getMessage().contains("immutable") || ex.getMessage().contains("integrity violation"),
                "Exception message should indicate immutability or integrity violation, got: " + ex.getMessage());
    }

    @Test
    void testResponseHashIsHexAndRecomputable() {
        Map<String, Object> payload = Map.of("data", "hex-test");
        DppRevisionRequestDTO req = DppRevisionRequestDTO.builder()
                .schemaVersion(DppRevisionSchemaDTO.builder()
                        .subjectType("TestType")
                        .majorVersion(1)
                        .minorVersion(0)
                        .build())
                .dppPayload(payload)
                .build();

        DppRevisionResponseDTO resp = dppRevisionService.reviseExistingDpp(testDpp.getDppId(), req);
        String hash = resp.getPayloadHash();

        assertNotNull(hash, "Hash should not be null");
        // Lowercase hex check
        assertTrue(hash.matches("^[0-9a-f]+$"), "Hash should be a lowercase hex string, got: " + hash);
        // SHA-256 in hex is 64 chars
        assertEquals(64, hash.length(), "SHA-256 hex should be 64 characters");

        // Recompute hash from returned payload
        @SuppressWarnings("unchecked")
        Map<String, Object> returnedPayload = (Map<String, Object>) resp.getDppPayload();
        byte[] recomputedHashBytes = ch.bfh.generic_dpp_platform.dpps.utils.DppUtil.hashDocument(returnedPayload);
        String recomputedHashHex = ch.bfh.generic_dpp_platform.dpps.utils.DppUtil.hashToHex(recomputedHashBytes);

        assertEquals(recomputedHashHex, hash, "Returned hash should match recomputed hash from payload");
    }

    @Test
    void testRevisionEndpointHashConsistency() {
        // Create a revision
        DppRevisionRequestDTO req = DppRevisionRequestDTO.builder()
                .schemaVersion(DppRevisionSchemaDTO.builder()
                        .subjectType("TestType")
                        .majorVersion(1)
                        .minorVersion(0)
                        .build())
                .dppPayload(Map.of("data", "consistency-test"))
                .build();
        DppRevisionResponseDTO created = dppRevisionService.reviseExistingDpp(testDpp.getDppId(), req);
        
        // Get current revision
        DppRevisionResponseDTO current = dppRevisionService.getCurrentDppRevision(testDpp.getDppId());
        
        // Get exact revision
        DppRevisionResponseDTO exact = dppRevisionService.getDppRevision(testDpp.getDppId(), created.getVersion());
        
        assertEquals(created.getPayloadHash(), current.getPayloadHash(), "Created hash should match current revision hash");
        assertEquals(created.getPayloadHash(), exact.getPayloadHash(), "Created hash should match exact revision hash");
        assertTrue(current.getPayloadHash().matches("^[0-9a-f]{64}$"), "Hash should be 64-char lowercase hex");
    }
}
