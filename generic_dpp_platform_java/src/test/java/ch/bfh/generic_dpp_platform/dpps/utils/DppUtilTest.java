package ch.bfh.generic_dpp_platform.dpps.utils;

import ch.bfh.generic_dpp_platform.schemas.models.DppSchema;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class DppUtilTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void testValidateDppDocument_Success() throws Exception {
        // Arrange
        String schemaJson = """
                {
                  "$schema": "https://json-schema.org/draft/2020-12/schema",
                  "type": "object",
                  "properties": {
                    "name": { "type": "string" },
                    "age": { "type": "integer" },
                    "tags": { 
                      "type": "array",
                      "items": { "type": "string" }
                    },
                    "metadata": {
                      "type": "object",
                      "properties": {
                        "active": { "type": "boolean" }
                      }
                    }
                  },
                  "required": ["name"]
                }
                """;
        JsonNode schemaNode = objectMapper.readTree(schemaJson);
        DppSchema dppSchema = DppSchema.builder()
                .schemaDocument(schemaNode)
                .build();

        Map<String, Object> payload = new HashMap<>();
        payload.put("name", "John Doe");
        payload.put("age", 30);
        payload.put("tags", java.util.List.of("tag1", "tag2"));
        payload.put("metadata", Map.of("active", true));

        // Act
        Map<String, Object> result = DppUtil.validateDppDocument(payload, dppSchema);

        // Assert
        assertEquals("John Doe", result.get("name"));
        assertEquals(30, result.get("age"));
        assertTrue(result.get("tags") instanceof java.util.List);
        assertEquals(true, ((Map)result.get("metadata")).get("active"));
    }

    @Test
    void testValidateDppDocument_Failure() throws Exception {
        // Arrange
        String schemaJson = """
                {
                  "$schema": "https://json-schema.org/draft/2020-12/schema",
                  "type": "object",
                  "properties": {
                    "name": { "type": "string" }
                  },
                  "required": ["name"]
                }
                """;
        JsonNode schemaNode = objectMapper.readTree(schemaJson);
        DppSchema dppSchema = DppSchema.builder()
                .schemaDocument(schemaNode)
                .build();

        Map<String, Object> payload = new HashMap<>();
        // missing required "name"

        // Act & Assert
        assertThrows(IllegalArgumentException.class, () -> DppUtil.validateDppDocument(payload, dppSchema));
    }

    @Test
    void testValidateDppDocument_ConstraintsFailure() throws Exception {
        // Arrange
        String schemaJson = """
                {
                  "$schema": "https://json-schema.org/draft/2020-12/schema",
                  "type": "object",
                  "properties": {
                    "code": { "type": "string", "pattern": "^[A-Z]{3}$" },
                    "score": { "type": "integer", "minimum": 0, "maximum": 100 }
                  }
                }
                """;
        JsonNode schemaNode = objectMapper.readTree(schemaJson);
        DppSchema dppSchema = DppSchema.builder()
                .schemaDocument(schemaNode)
                .build();

        // Invalid pattern
        Map<String, Object> payload1 = Map.of("code", "abc");
        assertThrows(IllegalArgumentException.class, () -> DppUtil.validateDppDocument(payload1, dppSchema));

        // Invalid minimum
        Map<String, Object> payload2 = Map.of("score", -1);
        assertThrows(IllegalArgumentException.class, () -> DppUtil.validateDppDocument(payload2, dppSchema));

        // Invalid maximum
        Map<String, Object> payload3 = Map.of("score", 101);
        assertThrows(IllegalArgumentException.class, () -> DppUtil.validateDppDocument(payload3, dppSchema));
    }

    @Test
    void testValidateDppDocument_AdditionalPropertiesFailure() throws Exception {
        // Arrange
        String schemaJson = """
                {
                  "$schema": "https://json-schema.org/draft/2020-12/schema",
                  "type": "object",
                  "properties": {
                    "name": { "type": "string" }
                  },
                  "additionalProperties": false
                }
                """;
        JsonNode schemaNode = objectMapper.readTree(schemaJson);
        DppSchema dppSchema = DppSchema.builder()
                .schemaDocument(schemaNode)
                .build();

        Map<String, Object> payload = Map.of("name", "Valid", "extra", "Invalid");

        // Act & Assert
        assertThrows(IllegalArgumentException.class, () -> DppUtil.validateDppDocument(payload, dppSchema));
    }

    @Test
    void testValidateDppDocument_NestedRequiredFailure() throws Exception {
        // Arrange
        String schemaJson = """
                {
                  "$schema": "https://json-schema.org/draft/2020-12/schema",
                  "type": "object",
                  "properties": {
                    "nested": {
                      "type": "object",
                      "properties": {
                        "inner": { "type": "string" }
                      },
                      "required": ["inner"]
                    }
                  }
                }
                """;
        JsonNode schemaNode = objectMapper.readTree(schemaJson);
        DppSchema dppSchema = DppSchema.builder()
                .schemaDocument(schemaNode)
                .build();

        Map<String, Object> payload = Map.of("nested", Map.of());

        // Act & Assert
        assertThrows(IllegalArgumentException.class, () -> DppUtil.validateDppDocument(payload, dppSchema));
    }

    @Test
    void testHashDocument_ComplexDeterministic() throws Exception {
        // Arrange
        Map<String, Object> doc = new HashMap<>();
        doc.put("b", 2);
        doc.put("a", 1);
        doc.put("nested", Map.of("z", 26, "y", 25));
        doc.put("list", java.util.List.of(Map.of("k2", "v2", "k1", "v1")));

        // Act
        byte[] hash1 = DppUtil.hashDocument(doc);
        
        // Construct same content but different order
        Map<String, Object> doc2 = new HashMap<>();
        doc2.put("nested", Map.of("y", 25, "z", 26));
        doc2.put("a", 1);
        doc2.put("list", java.util.List.of(Map.of("k1", "v1", "k2", "v2")));
        doc2.put("b", 2);
        
        byte[] hash2 = DppUtil.hashDocument(doc2);

        // Assert
        assertArrayEquals(hash1, hash2);
        assertEquals(32, hash1.length);
    }

    @Test
    void testHashDocument_DifferentContent() throws Exception {
        // Arrange
        Map<String, Object> doc1 = Map.of("a", 1);
        Map<String, Object> doc2 = Map.of("a", 2);

        // Act
        byte[] hash1 = DppUtil.hashDocument(doc1);
        byte[] hash2 = DppUtil.hashDocument(doc2);

        // Assert
        assertFalse(java.util.Arrays.equals(hash1, hash2));
    }

    @Test
    void testHexConversion() {
        byte[] hash = new byte[]{0, 1, 15, 16, 127, (byte) 128, (byte) 255};
        String hex = DppUtil.hashToHex(hash);
        assertEquals("00010f107f80ff", hex);
        
        byte[] back = DppUtil.hexToHash(hex);
        assertArrayEquals(hash, back);
    }

    @Test
    void testHexConversion_Null() {
        assertNull(DppUtil.hashToHex(null));
        assertNull(DppUtil.hexToHash(null));
    }

    @Test
    void testHexToHash_Invalid() {
        assertThrows(IllegalArgumentException.class, () -> DppUtil.hexToHash("not-hex"));
        assertThrows(IllegalArgumentException.class, () -> DppUtil.hexToHash("a")); // odd length
    }
}
