package ch.bfh.generic_dpp_platform.admin.controllers;

import ch.bfh.generic_dpp_platform.ControllerTest;
import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import ch.bfh.generic_dpp_platform.dpps.repositories.DppRevisionRepository;
import ch.bfh.generic_dpp_platform.dpps.utils.DppUtil;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchema;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchemaId;
import ch.bfh.generic_dpp_platform.schemas.repositories.DppSchemaRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

public class AdminImportControllerTest extends ControllerTest {

    private static final String SUBJECT_TYPE = "Battery";
    private static final ObjectMapper MAPPER = new ObjectMapper().findAndRegisterModules();

    @Autowired
    private SubjectTypeRepository subjectTypeRepository;

    @Autowired
    private DppSchemaRepository dppSchemaRepository;

    @Autowired
    private DppRevisionRepository dppRevisionRepository;

    @Test
    public void testImportRevisions_HappyPath_StoresReadableRevision() throws Exception {
        seedSubjectTypeAndSchema();
        Map<String, Object> payload = Map.of("name", "imported", "capacity_kwh", 12);
        String dppId = "issuerB-import-001";

        JsonNode response = postImport(List.of(importedRevision(dppId, 1, payload, hash(payload))));
        assertEquals(dppId, response.get(0).get("dpp_id").asText());
        assertEquals(1, response.get(0).get("version").asInt());

        JsonNode stored = MAPPER.readTree(getResponseAsString("/dpps/" + dppId + "/1"));
        assertEquals(dppId, stored.get("dpp_id").asText());
        assertEquals(hash(payload), stored.get("payload_hash").asText());
        assertEquals("imported", stored.get("dpp_payload").get("name").asText());
    }

    @Test
    public void testImportRevisions_RetryIsIdempotent() throws Exception {
        seedSubjectTypeAndSchema();
        Map<String, Object> payload = Map.of("name", "retry", "capacity_kwh", 9);
        String dppId = "issuerB-import-retry";
        String json = MAPPER.writeValueAsString(List.of(importedRevision(dppId, 1, payload, hash(payload))));

        postImport(json);
        postImport(json);

        assertEquals(1, dppRevisionRepository.findAllByIdDppIdOrderByIdDppVersionAsc(dppId).size());
    }

    @Test
    public void testImportRevisions_HashMismatch_ReturnsBadRequest() throws Exception {
        seedSubjectTypeAndSchema();
        Map<String, Object> payload = Map.of("name", "tampered", "capacity_kwh", 7);
        String dppId = "issuerB-import-bad-hash";
        String json = MAPPER.writeValueAsString(List.of(importedRevision(dppId, 1, payload, "00")));

        postErrorStatusCode("/admin/import-revisions", json, HttpStatus.BAD_REQUEST);
        getErrorStatusCode("/dpps/" + dppId + "/1", HttpStatus.NOT_FOUND);
    }

    @Test
    public void testImportRevisions_MissingCachedSchema_ReturnsNotFound() throws Exception {
        seedSubjectTypeOnly();
        Map<String, Object> payload = Map.of("name", "missing schema", "capacity_kwh", 3);
        String json = MAPPER.writeValueAsString(List.of(importedRevision("issuerB-import-missing-schema", 1, payload, hash(payload))));

        postErrorStatusCode("/admin/import-revisions", json, HttpStatus.NOT_FOUND);
    }

    private JsonNode postImport(List<Map<String, Object>> revisions) throws Exception {
        return postImport(MAPPER.writeValueAsString(revisions));
    }

    private JsonNode postImport(String json) throws Exception {
        String response = sendRequestAndExpectString(
                post("/admin/import-revisions")
                        .content(json)
                        .contentType(MediaType.APPLICATION_JSON),
                HttpStatus.OK
        );
        return MAPPER.readTree(response);
    }

    private Map<String, Object> importedRevision(
            String dppId,
            int version,
            Map<String, Object> payload,
            String payloadHash
    ) {
        return Map.of(
                "dpp_id", dppId,
                "version", version,
                "schema_version", Map.of(
                        "subject_type", SUBJECT_TYPE,
                        "major_version", 1,
                        "minor_version", 0
                ),
                "dpp_payload", payload,
                "payload_hash", payloadHash,
                "created_at", "2026-01-01T00:00:00Z"
        );
    }

    private void seedSubjectTypeAndSchema() throws Exception {
        SubjectType subjectType = seedSubjectTypeOnly();
        DppSchema schema = DppSchema.builder()
                .id(DppSchemaId.builder()
                        .subjectTypeName(SUBJECT_TYPE)
                        .majorVersion(1)
                        .minorVersion(0)
                        .build())
                .subjectType(subjectType)
                .schemaDocument(MAPPER.readTree("""
                        {
                          "$schema": "https://json-schema.org/draft/2020-12/schema",
                          "type": "object",
                          "properties": {
                            "name": { "type": "string" },
                            "capacity_kwh": { "type": "number" }
                          },
                          "required": ["name"],
                          "additionalProperties": false
                        }
                        """))
                .publishedAt(Instant.now())
                .build();
        dppSchemaRepository.save(schema);
    }

    private SubjectType seedSubjectTypeOnly() {
        return subjectTypeRepository.save(SubjectType.builder()
                .name(SUBJECT_TYPE)
                .description("Battery subject type")
                .build());
    }

    private String hash(Map<String, Object> payload) {
        return DppUtil.hashToHex(DppUtil.hashDocument(payload));
    }
}
