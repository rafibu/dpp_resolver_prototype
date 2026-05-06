package ch.bfh.generic_dpp_platform.dpps.utils;

import ch.bfh.generic_dpp_platform.dpps.models.DppReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Utility for extracting DPP references from JSON payloads.
 * Traverses arbitrary JSON objects and arrays to find objects containing "$ref".
 */
@Slf4j
@Component
public class DppReferenceExtractor {

    // Format: subject_type/issuer-local_id[/version]
    // issuer-local_id can contain hyphens, alphanumeric characters.
    private static final Pattern REF_PATTERN = Pattern.compile("^([^/]+)/([^/]+)(?:/(\\d+))?$");

    /**
     * Extracts all DPP references from a JSON node.
     *
     * @param node The JSON node to traverse.
     * @return A list of extracted DppReference objects.
     */
    public List<DppReference> extractReferences(JsonNode node) {
        List<DppReference> references = new ArrayList<>();
        traverse(node, "$", references);
        return references;
    }

    private void traverse(JsonNode node, String path, List<DppReference> references) {
        if (node.isObject()) {
            ObjectNode objectNode = (ObjectNode) node;
            if (objectNode.has("$ref")) {
                DppReference ref = parseReference(objectNode, path);
                if (ref != null) {
                    references.add(ref);
                }
            } else {
                Iterator<Map.Entry<String, JsonNode>> fields = objectNode.fields();
                while (fields.hasNext()) {
                    Map.Entry<String, JsonNode> entry = fields.next();
                    traverse(entry.getValue(), path + "." + entry.getKey(), references);
                }
            }
        } else if (node.isArray()) {
            ArrayNode arrayNode = (ArrayNode) node;
            for (int i = 0; i < arrayNode.size(); i++) {
                traverse(arrayNode.get(i), path + "[" + i + "]", references);
            }
        }
    }

    private DppReference parseReference(ObjectNode node, String path) {
        JsonNode refNode = node.get("$ref");
        if (!refNode.isTextual()) {
            throw new IllegalArgumentException("Invalid reference at " + path + ": $ref must be a string");
        }

        String originalRef = refNode.asText();
        Matcher matcher = REF_PATTERN.matcher(originalRef);

        if (!matcher.matches()) {
            throw new IllegalArgumentException("Invalid reference format at " + path + ": " + originalRef + ". Expected format: subject_type/dpp_id[/version]");
        }

        String subjectType = matcher.group(1);
        String dppId = matcher.group(2);
        String versionStr = matcher.group(3);
        Integer version = null;

        if (versionStr != null) {
            version = Integer.parseInt(versionStr);
        }

        // Check if version is provided as a separate field
        if (node.has("version")) {
            JsonNode versionNode = node.get("version");
            if (!versionNode.isInt()) {
                throw new IllegalArgumentException("Invalid reference at " + path + ": version must be an integer");
            }
            int extraVersion = versionNode.asInt();
            if (version != null && !version.equals(extraVersion)) {
                 throw new IllegalArgumentException("Conflicting versions in reference at " + path + ": " + originalRef + " and version " + extraVersion);
            }
            version = extraVersion;
        }

        DppReference.DependencyType type = (version != null) ? DppReference.DependencyType.HARD : DppReference.DependencyType.SOFT;

        return DppReference.builder()
                .subjectType(subjectType)
                .dppId(dppId)
                .version(version)
                .type(type)
                .originalRef(originalRef)
                .jsonPath(path)
                .build();
    }
}
