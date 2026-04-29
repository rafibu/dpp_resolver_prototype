package ch.bfh.dpp_resolver.utils;

import com.fasterxml.jackson.databind.JsonNode;
import lombok.extern.slf4j.Slf4j;

import java.util.Iterator;
import java.util.LinkedHashSet;
import java.util.Set;

/**
 *
 * @author rbu on 20.04.2026
 */
@Slf4j
public class JsonUtil {

    /**
     * Asserts that the new schema is backwards compatible with the old schema.
     * A schema is backwards compatible if no fields are removed and no additional mandatory fields are introduced
     * @param oldSchema currently active schema
     * @param newSchema new schema to be validated
     */
    public static void assertIsBackwardsCompatible(JsonNode oldSchema, JsonNode newSchema) {
        validateCompatibility(oldSchema, newSchema, "$");
    }

    private static void validateCompatibility(JsonNode oldSchema, JsonNode newSchema, String path) {
        JsonNode oldProperties = oldSchema.get("properties");
        JsonNode newProperties = newSchema.get("properties");

        if (oldProperties == null || newProperties == null || !oldProperties.isObject() || !newProperties.isObject()) {
            return;
        }

        Set<String> oldFieldNames = fieldNames(oldProperties);
        Set<String> newFieldNames = fieldNames(newProperties);

        // 1) Check removed fields
        for (String fieldName : oldFieldNames) {
            if (!newFieldNames.contains(fieldName)) {
                throw new IllegalArgumentException("Incompatible schema: field removed at " + path + "." + fieldName);
            }
        }

        // 2) Check newly introduced mandatory fields
        Set<String> newRequiredFields = requiredFieldNames(newSchema.get("required"));
        for (String fieldName : newFieldNames) {
            if (!oldFieldNames.contains(fieldName) && newRequiredFields.contains(fieldName)) {
                throw new IllegalArgumentException("Incompatible schema: new mandatory field introduced at " + path + "." + fieldName);
            }
        }

        // 3) Recurse into nested object properties
        for (String fieldName : oldFieldNames) {
            JsonNode oldChild = oldProperties.get(fieldName);
            JsonNode newChild = newProperties.get(fieldName);

            if (oldChild != null && newChild != null
                    && "object".equals(oldChild.path("type").asText())
                    && "object".equals(newChild.path("type").asText())) {
                validateCompatibility(oldChild, newChild, path + "." + fieldName);
            }
        }
    }

    private static Set<String> fieldNames(JsonNode propertiesNode) {
        Set<String> fieldNames = new LinkedHashSet<>();
        Iterator<String> names = propertiesNode.fieldNames();
        while (names.hasNext()) {
            fieldNames.add(names.next());
        }
        return fieldNames;
    }

    private static Set<String> requiredFieldNames(JsonNode requiredNode) {
        Set<String> requiredFields = new LinkedHashSet<>();
        if (requiredNode != null && requiredNode.isArray()) {
            for (JsonNode node : requiredNode) {
                if (node.isTextual()) {
                    requiredFields.add(node.asText());
                }
            }
        }
        return requiredFields;
    }
}
