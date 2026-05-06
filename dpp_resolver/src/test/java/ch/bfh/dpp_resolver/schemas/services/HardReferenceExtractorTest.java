package ch.bfh.dpp_resolver.schemas.services;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class HardReferenceExtractorTest {

    private final HardReferenceExtractor extractor = new HardReferenceExtractor();
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void testNoReferences() throws Exception {
        JsonNode schema = mapper.readTree("""
            {
              "type": "object",
              "properties": {
                "name": { "type": "string" }
              }
            }
            """);
        List<String> targets = extractor.extractHardReferenceTargets(schema);
        assertTrue(targets.isEmpty());
    }

    @Test
    void testDirectReference() throws Exception {
        JsonNode schema = mapper.readTree("""
            {
              "type": "object",
              "properties": {
                "battery": {
                  "type": "object",
                  "x-dpp-reference": "battery",
                  "properties": {
                    "$ref": { "type": "string" },
                    "version": { "type": "integer" }
                  }
                }
              }
            }
            """);
        List<String> targets = extractor.extractHardReferenceTargets(schema);
        assertEquals(1, targets.size());
        assertTrue(targets.contains("battery"));
    }

    @Test
    void testMultipleReferences() throws Exception {
        JsonNode schema = mapper.readTree("""
            {
              "type": "object",
              "properties": {
                "battery": { "x-dpp-reference": "battery" },
                "inverter": { "x-dpp-reference": "inverter" }
              }
            }
            """);
        List<String> targets = extractor.extractHardReferenceTargets(schema);
        assertEquals(2, targets.size());
        assertTrue(targets.contains("battery"));
        assertTrue(targets.contains("inverter"));
    }

    @Test
    void testDeduplication() throws Exception {
        JsonNode schema = mapper.readTree("""
            {
              "type": "object",
              "properties": {
                "battery1": { "x-dpp-reference": "battery" },
                "battery2": { "x-dpp-reference": "battery" }
              }
            }
            """);
        List<String> targets = extractor.extractHardReferenceTargets(schema);
        assertEquals(1, targets.size());
        assertTrue(targets.contains("battery"));
    }

    @Test
    void testNestedReferences() throws Exception {
        JsonNode schema = mapper.readTree("""
            {
              "type": "object",
              "properties": {
                "components": {
                  "type": "array",
                  "items": {
                    "type": "object",
                    "properties": {
                       "sub": { "x-dpp-reference": "part" }
                    }
                  }
                }
              }
            }
            """);
        // Note: Our walk only walks properties and definitions, it doesn't walk into "items" currently
        // unless we call walk on it. The current implementation walks properties of the root.
        // Let's see if we should extend it.
        // Task 2: "Walk only properties and definitions/$defs; do not recurse into oneOf/anyOf for now"
        // It didn't mention "items".
        
        List<String> targets = extractor.extractHardReferenceTargets(schema);
        // Based on current implementation, it should be empty because it doesn't walk into "items"
        assertTrue(targets.isEmpty());
    }

    @Test
    void testDefinitionsReferences() throws Exception {
        JsonNode schema = mapper.readTree("""
            {
              "type": "object",
              "definitions": {
                "battery": { "x-dpp-reference": "battery" }
              },
              "$defs": {
                "inverter": { "x-dpp-reference": "inverter" }
              }
            }
            """);
        List<String> targets = extractor.extractHardReferenceTargets(schema);
        assertEquals(2, targets.size());
        assertTrue(targets.contains("battery"));
        assertTrue(targets.contains("inverter"));
    }

    @Test
    void testInvalidAnnotationType() throws Exception {
        JsonNode schema = mapper.readTree("""
            {
              "properties": {
                "battery": { "x-dpp-reference": 123 }
              }
            }
            """);
        assertThrows(IllegalArgumentException.class, () -> extractor.extractHardReferenceTargets(schema));
    }
}
