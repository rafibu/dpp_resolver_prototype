package ch.bfh.dpp_resolver.schemas.services;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * Extracts hard-reference targets from a JSON Schema document.
 * Follows the convention defined in docs/schema-conventions.md.
 */
@Component
public class HardReferenceExtractor {

    private static final String REFERENCE_ANNOTATION = "x-dpp-reference";

    public List<String> extractHardReferenceTargets(JsonNode schemaDocument) {
        Set<String> targets = new HashSet<>();
        if (schemaDocument == null) {
            return new ArrayList<>();
        }

        if (schemaDocument.has(REFERENCE_ANNOTATION)) {
             if (!schemaDocument.isObject()) {
                 // Technically this shouldn't happen with Jackson if it has fields, but for completeness:
                 throw new IllegalArgumentException(REFERENCE_ANNOTATION + " found at non-object level");
             }
             extractFromNode(schemaDocument, targets);
        }

        walk(schemaDocument, targets);

        return new ArrayList<>(targets);
    }

    private void walk(JsonNode node, Set<String> targets) {
        if (node == null || !node.isObject()) {
            return;
        }

        // Walk properties
        if (node.has("properties") && node.get("properties").isObject()) {
            JsonNode properties = node.get("properties");
            properties.fieldNames().forEachRemaining(fieldName -> {
                JsonNode property = properties.get(fieldName);
                extractFromNode(property, targets);
                walk(property, targets);
            });
        }

        // Walk definitions/$defs
        if (node.has("definitions") && node.get("definitions").isObject()) {
            JsonNode definitions = node.get("definitions");
            definitions.fieldNames().forEachRemaining(fieldName -> {
                JsonNode definition = definitions.get(fieldName);
                extractFromNode(definition, targets);
                walk(definition, targets);
            });
        }
        if (node.has("$defs") && node.get("$defs").isObject()) {
            JsonNode defs = node.get("$defs");
            defs.fieldNames().forEachRemaining(fieldName -> {
                JsonNode def = defs.get(fieldName);
                extractFromNode(def, targets);
                walk(def, targets);
            });
        }
    }

    private void extractFromNode(JsonNode node, Set<String> targets) {
        if (node.has(REFERENCE_ANNOTATION)) {
            if (!node.isObject()) {
                throw new IllegalArgumentException(REFERENCE_ANNOTATION + " found at non-object level");
            }
            JsonNode annotationValue = node.get(REFERENCE_ANNOTATION);
            if (!annotationValue.isTextual()) {
                throw new IllegalArgumentException(REFERENCE_ANNOTATION + " must be a string");
            }
            targets.add(annotationValue.asText());
        }
    }
}
