package ch.bfh.generic_dpp_platform.dpps.utils;

import ch.bfh.generic_dpp_platform.dpps.exceptions.SchemaValidationException;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchema;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.networknt.schema.JsonSchema;
import com.networknt.schema.JsonSchemaFactory;
import com.networknt.schema.SpecVersion;
import com.networknt.schema.ValidationMessage;
import org.erdtman.jcs.JsonCanonicalizer;

import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * Utility class for Digital Product Passport (DPP) document operations,
 * including validation against JSON schemas and deterministic hashing.
 *
 * @author rbu on 02.05.2026
 */
public class DppUtil {
    private static final ObjectMapper objectMapper = new ObjectMapper();

    /**
     * This method operationalizes Invariant 5 "Schema conformance" <br>
     * Validates a DPP payload against a provided JSON schema.
     * The validation follows the JSON Schema 2020-12 specification.
     * It also performs a preliminary check for DPP references within the payload.
     *
     * @param dppPayload the document payload to validate (e.g., a Map or DTO)
     * @param dppSchema  the {@link DppSchema} containing the JSON schema definition
     * @return the validated payload as a Map
     * @throws IllegalArgumentException if the document fails validation against the schema
     */
    public static Map<String, Object> validateDppDocument(Object dppPayload, DppSchema dppSchema) {
        JsonNode payloadNode = objectMapper.valueToTree(dppPayload);
        JsonNode schemaNode = dppSchema.getSchemaDocument();

        JsonSchemaFactory factory = JsonSchemaFactory.getInstance(SpecVersion.VersionFlag.V202012);
        JsonSchema schema = factory.getSchema(schemaNode);

        Set<ValidationMessage> errors = schema.validate(payloadNode);

        if (!errors.isEmpty()) {
            List<String> errorMessages = errors.stream()
                    .map(ValidationMessage::getMessage)
                    .collect(Collectors.toList());
            throw new SchemaValidationException("DPP Document validation failed", errorMessages);
        }

        return objectMapper.convertValue(payloadNode, new TypeReference<>() {
        });
    }

    /**
     * Computes a SHA-256 hash of the provided DPP document.
     * The document is first canonicalized using the JSON Canonicalization Scheme (JCS)
     * as defined in RFC 8785 to ensure the hash is deterministic regardless of key order
     * or whitespace in the input.
     *
     * @param validDppDocument the validated DPP document as a Map
     * @return a byte array containing the SHA-256 hash
     * @throws IllegalArgumentException if the hashing process fails
     */
    public static byte[] hashDocument(Map<String, Object> validDppDocument) {
        try {
            String json = objectMapper.writeValueAsString(validDppDocument);
            JsonCanonicalizer jc = new JsonCanonicalizer(json);
            byte[] canonicalBytes = jc.getEncodedUTF8();

            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return digest.digest(canonicalBytes);
        } catch (Exception e) {
            throw new IllegalArgumentException("Failed to hash DPP document", e);
        }
    }

    /**
     * Converts a byte array hash to a lowercase hexadecimal string.
     *
     * @param hash the byte array to convert
     * @return a lowercase hexadecimal string representation
     */
    public static String hashToHex(byte[] hash) {
        if (hash == null) return null;
        return HexFormat.of().formatHex(hash);
    }

    /**
     * Converts a hexadecimal string back to a byte array.
     *
     * @param hex the hexadecimal string to convert
     * @return the byte array representation
     * @throws IllegalArgumentException if the hex string is invalid
     */
    public static byte[] hexToHash(String hex) {
        if (hex == null) return null;
        try {
            return HexFormat.of().parseHex(hex);
        } catch (IllegalArgumentException e) {
            throw new IllegalArgumentException("Invalid hexadecimal string: " + hex, e);
        }
    }
}
