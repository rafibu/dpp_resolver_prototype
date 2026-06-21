package ch.bfh.generic_dpp_platform.queries.helpers;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 *
 * @author rbu on 21.06.2026
 */
public class PredicateQueryHelper {

    private static final String PATH_SEPARATOR = "\\.";

    /**
     * Resolves a value from a nested map structure based on a specified path.
     *
     * @param document the root map that contains the nested structure
     * @param path     a dot-separated string representing the path to the desired value
     * @return the value located at the specified path, or null if the path is invalid or not found
     */
    public static Object resolvePath(Map<String, Object> document, String path) {
        if (document == null || path == null || path.isBlank()) {
            return null;
        }

        String[] pathElements = path.split(PATH_SEPARATOR);
        Object current = document;
        for (String pathElement : pathElements) {
            if (current instanceof Map<?, ?> map) {
                current = map.get(pathElement);
            } else {
                return null;
            }
        }
        return current;
    }

    /**
     * Projects the document to the requested return fields.
     * <p>
     * If no return fields are specified, the complete document is returned.
     * Nested field paths are resolved using dot notation.
     * </p>
     *
     * @param document     the source document
     * @param returnFields field paths to include; if null or empty, all fields are included
     * @return the complete document or a projected map containing the requested fields
     */
    public static Map<String, Object> selectFields(Map<String, Object> document, List<String> returnFields) {
        if (returnFields == null || returnFields.isEmpty()) {
            return document;
        }

        Map<String, Object> filteredDocument = new LinkedHashMap<>();
        for (String field : returnFields) {
            Object value = resolvePath(document, field);
            if (value != null) {
                filteredDocument.put(field, value);
            }
        }
        return filteredDocument;
    }
}
