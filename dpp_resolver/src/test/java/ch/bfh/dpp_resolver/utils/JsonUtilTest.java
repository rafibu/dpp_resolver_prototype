package ch.bfh.dpp_resolver.utils;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * @author rbu on 21.04.2026
 */
class JsonUtilTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @Test
    void assertIsBackwardsCompatible_happyPath_whenOnlyOptionalFieldIsAdded() throws Exception {
        JsonNode oldSchema = MAPPER.readTree("""
            {
              "type": "object",
              "properties": {
                "name": { "type": "string" }
              },
              "required": ["name"]
            }
            """);

        JsonNode newSchema = MAPPER.readTree("""
            {
              "type": "object",
              "properties": {
                "name": { "type": "string" },
                "description": { "type": "string" }
              },
              "required": ["name"]
            }
            """);

        assertDoesNotThrow(() -> JsonUtil.assertIsBackwardsCompatible(oldSchema, newSchema));
    }

    @Test
    void assertIsBackwardsCompatible_throws_whenOldFieldWasRemoved() throws Exception {
        JsonNode oldSchema = MAPPER.readTree("""
            {
              "type": "object",
              "properties": {
                "name": { "type": "string" },
                "description": { "type": "string" }
              },
              "required": ["name"]
            }
            """);

        JsonNode newSchema = MAPPER.readTree("""
            {
              "type": "object",
              "properties": {
                "name": { "type": "string" }
              },
              "required": ["name"]
            }
            """);

        assertThrows(IllegalArgumentException.class,
                () -> JsonUtil.assertIsBackwardsCompatible(oldSchema, newSchema));
    }

    @Test
    void assertIsBackwardsCompatible_throws_whenNewMandatoryFieldWasIntroduced() throws Exception {
        JsonNode oldSchema = MAPPER.readTree("""
            {
              "type": "object",
              "properties": {
                "name": { "type": "string" }
              },
              "required": ["name"]
            }
            """);

        JsonNode newSchema = MAPPER.readTree("""
            {
              "type": "object",
              "properties": {
                "name": { "type": "string" },
                "version": { "type": "integer" }
              },
              "required": ["name", "version"]
            }
            """);

        assertThrows(IllegalArgumentException.class,
                () -> JsonUtil.assertIsBackwardsCompatible(oldSchema, newSchema));
    }
}