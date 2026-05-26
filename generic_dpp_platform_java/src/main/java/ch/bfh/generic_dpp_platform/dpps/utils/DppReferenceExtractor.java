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
 * Extracts DPP references from JSON payloads using the prototype's {@code $ref} convention.
 * <p>
 * The formal model defines reference extraction as schema-parameterized: a schema declares which payload
 * positions contain DPP references. This Java platform uses a simpler implementation convention: every JSON
 * object containing a textual {@code "$ref"} property is treated as a DPP reference.
 * </p>
 * <p>
 * Supported reference syntax:
 * </p>
 * <pre>
 * subject_type/issuer-local_id
 * subject_type/issuer-local_id/version
 * </pre>
 * <p>
 * A reference with a version is classified as a hard reference because it identifies a concrete immutable
 * revision. A reference without a version is classified as a soft reference because it identifies only the
 * logical DPP and may resolve dynamically to the current revision.
 * </p>
 * <p>
 * As an alternative encoding, the version may also be supplied in a sibling {@code "version"} property. If both
 * encodings are present, they must agree.
 * </p>
 */
@Slf4j
@Component
public class DppReferenceExtractor {

    // Format: subject_type/issuer-local_id[/version]
    // issuer-local_id can contain hyphens, alphanumeric characters.
    private static final Pattern REF_PATTERN = Pattern.compile("^([^/]+)/([^/]+)(?:/(\\d+))?$");

    /**
     * Extracts all DPP references from a JSON node.
     * <p>
     * The traversal is recursive and covers nested objects and arrays. When an object containing {@code "$ref"}
     * is found, that object is parsed as a reference and its children are not traversed further.
     * </p>
     *
     * @param node the JSON node to traverse
     * @return all extracted DPP references, including both hard and soft references
     * @throws IllegalArgumentException if a discovered {@code "$ref"} is malformed, non-textual, or has a
     *                                  conflicting separate {@code "version"} property
     */
    public List<DppReference> extractReferences(JsonNode node) {
        List<DppReference> references = new ArrayList<>();
        traverse(node, "$", references);
        return references;
    }

    /**
     * Recursively traverses a JSON subtree and records DPP references.
     *
     * @param node       the current JSON node
     * @param path       the JSON path of the current node, used for error reporting
     * @param references the mutable result list receiving extracted references
     */
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

    /**
     * Parses a JSON object containing {@code "$ref"} into a {@link DppReference}.
     * <p>
     * The hard/soft distinction is inferred from the presence of a version. If a version is present either in
     * the reference string or as a separate {@code "version"} field, the result is a hard reference. Otherwise,
     * the result is a soft reference.
     * </p>
     *
     * @param node the JSON object containing {@code "$ref"}
     * @param path the JSON path used in validation error messages
     * @return the parsed DPP reference
     * @throws IllegalArgumentException if the reference syntax is invalid
     */
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
