package ch.bfh.generic_dpp_platform.dpps.utils;

import ch.bfh.generic_dpp_platform.dpps.models.DppReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class DppReferenceExtractorTest {

    private final DppReferenceExtractor extractor = new DppReferenceExtractor();
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void testExtractHardReference() throws Exception {
        String json = "{\"$ref\": \"battery/issuerB-bat-001\", \"version\": 1}";
        List<DppReference> refs = extractor.extractReferences(mapper.readTree(json));
        assertEquals(1, refs.size());
        assertEquals("battery", refs.get(0).subjectType());
        assertEquals("issuerB-bat-001", refs.get(0).dppId());
        assertEquals(1, refs.get(0).version());
        assertEquals(DppReference.DependencyType.HARD, refs.get(0).type());
    }

    @Test
    void testExtractSoftReference() throws Exception {
        String json = "{\"$ref\": \"battery/issuerB-bat-001\"}";
        List<DppReference> refs = extractor.extractReferences(mapper.readTree(json));
        assertEquals(1, refs.size());
        assertEquals(DppReference.DependencyType.SOFT, refs.get(0).type());
        assertNull(refs.get(0).version());
    }

    @Test
    void testExtractToleratedHardReference() throws Exception {
        String json = "{\"$ref\": \"battery/issuerB-bat-001/1\"}";
        List<DppReference> refs = extractor.extractReferences(mapper.readTree(json));
        assertEquals(1, refs.size());
        assertEquals(1, refs.get(0).version());
        assertEquals(DppReference.DependencyType.HARD, refs.get(0).type());
    }

    @Test
    void testExtractNestedReferences() throws Exception {
        String json = """
            {
                "part1": {"$ref": "part/p-001", "version": 2},
                "components": [
                    {"$ref": "comp/c-001"},
                    {"details": {"$ref": "detail/d-001", "version": 5}}
                ]
            }
            """;
        List<DppReference> refs = extractor.extractReferences(mapper.readTree(json));
        assertEquals(3, refs.size());
        
        assertTrue(refs.stream().anyMatch(r -> r.dppId().equals("p-001") && r.type() == DppReference.DependencyType.HARD));
        assertTrue(refs.stream().anyMatch(r -> r.dppId().equals("c-001") && r.type() == DppReference.DependencyType.SOFT));
        assertTrue(refs.stream().anyMatch(r -> r.dppId().equals("d-001") && r.version() == 5));
    }

    @Test
    void testInvalidReferenceFormat() {
        String json = "{\"$ref\": \"invalid-format\"}";
        assertThrows(IllegalArgumentException.class, () -> {
            extractor.extractReferences(mapper.readTree(json));
        });
    }
}
