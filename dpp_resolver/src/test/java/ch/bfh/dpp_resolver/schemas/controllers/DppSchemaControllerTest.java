package ch.bfh.dpp_resolver.schemas.controllers;

import ch.bfh.dpp_resolver.ControllerTest;
import ch.bfh.dpp_resolver.admin.dto.SubjectTypeDTO;
import ch.bfh.dpp_resolver.schemas.dtos.DppSchemaDTO;
import ch.bfh.dpp_resolver.schemas.repositories.DppSchemaRepository;
import ch.bfh.dpp_resolver.admin.repositories.SubjectTypeRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;

import static org.junit.jupiter.api.Assertions.*;

class DppSchemaControllerTest extends ControllerTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void createAndGetSchema_happyPath() throws Exception {
        // 1. Create SubjectType
        SubjectTypeDTO st = new SubjectTypeDTO("Battery", "EV Battery");
        postResponseAsObject("/admin/subject-types", mapper.writeValueAsString(st), SubjectTypeDTO.class);

        // 2. Create first schema (1.0)
        JsonNode schema1 = mapper.readTree("{\"type\":\"object\",\"properties\":{\"id\":{\"type\":\"string\"}}}");
        DppSchemaDTO dto1 = DppSchemaDTO.builder()
                .subjectType("Battery")
                .majorVersion(1)
                .minorVersion(0)
                .schemaDocument(schema1)
                .build();

        postResponseAsObject("/schemas", mapper.writeValueAsString(dto1), DppSchemaDTO.class);

        // 3. Get active schema
        DppSchemaDTO active = getResponseAsObject("/schemas/Battery/current", DppSchemaDTO.class);
        assertEquals(1, active.getMajorVersion());
        assertEquals(0, active.getMinorVersion());
        assertEquals(mapper.writeValueAsString(schema1), mapper.writeValueAsString(active.getSchemaDocument()));

        // 4. Create minor update (1.1) - backwards compatible
        JsonNode schema11 = mapper.readTree("{\"type\":\"object\",\"properties\":{\"id\":{\"type\":\"string\"},\"capacity\":{\"type\":\"number\"}}}");
        DppSchemaDTO dto11 = DppSchemaDTO.builder()
                .subjectType("Battery")
                .majorVersion(1)
                .minorVersion(1)
                .schemaDocument(schema11)
                .build();
        
        postResponseAsObject("/schemas", mapper.writeValueAsString(dto11), DppSchemaDTO.class);

        // 5. Get active (should be 1.1)
        active = getResponseAsObject("/schemas/Battery/current", DppSchemaDTO.class);
        assertEquals(1, active.getMajorVersion());
        assertEquals(1, active.getMinorVersion());

        // 6. Get exact (1.0)
        DppSchemaDTO exact = getResponseAsObject("/schemas/Battery/1/0", DppSchemaDTO.class);
        assertEquals(0, exact.getMinorVersion());

        // 7. Create major update (2.0)
        JsonNode schema2 = mapper.readTree("{\"type\":\"object\",\"properties\":{\"serialNumber\":{\"type\":\"string\"}}}");
        DppSchemaDTO dto2 = DppSchemaDTO.builder()
                .subjectType("Battery")
                .majorVersion(2)
                .minorVersion(0)
                .schemaDocument(schema2)
                .build();

        postResponseAsObject("/schemas", mapper.writeValueAsString(dto2), DppSchemaDTO.class);

        active = getResponseAsObject("/schemas/Battery/current", DppSchemaDTO.class);
        assertEquals(2, active.getMajorVersion());
        assertEquals(0, active.getMinorVersion());
    }

    @Test
    void findAllSchemas_happyPath() throws Exception {
        // 1. Create SubjectType
        SubjectTypeDTO st = new SubjectTypeDTO("Battery", "EV Battery");
        postResponseAsObject("/admin/subject-types", mapper.writeValueAsString(st), SubjectTypeDTO.class);

        // 2. Create two schemas
        JsonNode schema1 = mapper.readTree("{\"type\":\"object\",\"properties\":{\"id\":{\"type\":\"string\"}}}");
        DppSchemaDTO dto1 = DppSchemaDTO.builder()
                .subjectType("Battery")
                .majorVersion(1)
                .minorVersion(0)
                .schemaDocument(schema1)
                .build();
        postResponseAsObject("/schemas", mapper.writeValueAsString(dto1), DppSchemaDTO.class);

        JsonNode schema11 = mapper.readTree("{\"type\":\"object\",\"properties\":{\"id\":{\"type\":\"string\"},\"cap\":{\"type\":\"number\"}}}");
        DppSchemaDTO dto11 = DppSchemaDTO.builder()
                .subjectType("Battery")
                .majorVersion(1)
                .minorVersion(1)
                .schemaDocument(schema11)
                .build();
        postResponseAsObject("/schemas", mapper.writeValueAsString(dto11), DppSchemaDTO.class);

        // 3. Find all
        DppSchemaDTO[] schemas = getResponseAsObject("/schemas/Battery", DppSchemaDTO[].class);
        assertEquals(2, schemas.length);
        assertEquals(0, schemas[0].getMinorVersion());
        assertEquals(1, schemas[1].getMinorVersion());
    }

    @Test
    void createSchema_shouldReturnBadRequest_whenIncompatibleMinorUpdate() throws Exception {
        // 1. Create SubjectType
        SubjectTypeDTO st = new SubjectTypeDTO("Battery", "EV Battery");
        postResponseAsObject("/admin/subject-types", mapper.writeValueAsString(st), SubjectTypeDTO.class);

        // 2. Create 1.0
        JsonNode schema1 = mapper.readTree("{\"type\":\"object\",\"properties\":{\"id\":{\"type\":\"string\"}}}");
        DppSchemaDTO dto1 = DppSchemaDTO.builder()
                .subjectType("Battery")
                .majorVersion(1)
                .minorVersion(0)
                .schemaDocument(schema1)
                .build();
        postResponseAsObject("/schemas", mapper.writeValueAsString(dto1), DppSchemaDTO.class);

        // 3. Create incompatible 1.1 (removed field 'id')
        JsonNode schema11 = mapper.readTree("{\"type\":\"object\",\"properties\":{\"newId\":{\"type\":\"string\"}}}");
        DppSchemaDTO dto11 = DppSchemaDTO.builder()
                .subjectType("Battery")
                .majorVersion(1)
                .minorVersion(1)
                .schemaDocument(schema11)
                .build();
        
        postErrorStatusCode("/schemas", mapper.writeValueAsString(dto11), HttpStatus.BAD_REQUEST);
    }

    @Test
    void createSchema_shouldReturnBadRequest_whenInvalidVersionIncrement() throws Exception {
        SubjectTypeDTO st = new SubjectTypeDTO("Battery", "EV Battery");
        postResponseAsObject("/admin/subject-types", mapper.writeValueAsString(st), SubjectTypeDTO.class);

        JsonNode schema = mapper.readTree("{\"type\":\"object\"}");
        DppSchemaDTO dto1 = DppSchemaDTO.builder()
                .subjectType("Battery")
                .majorVersion(1)
                .minorVersion(0)
                .schemaDocument(schema)
                .build();
        postResponseAsObject("/schemas", mapper.writeValueAsString(dto1), DppSchemaDTO.class);

        // Try to skip a minor version (1.2 instead of 1.1)
        DppSchemaDTO dto12 = DppSchemaDTO.builder()
                .subjectType("Battery")
                .majorVersion(1)
                .minorVersion(2)
                .schemaDocument(schema)
                .build();
        postErrorStatusCode("/schemas", mapper.writeValueAsString(dto12), HttpStatus.BAD_REQUEST);

        // Try to skip a major version (3.0 instead of 2.0)
        DppSchemaDTO dto3 = DppSchemaDTO.builder()
                .subjectType("Battery")
                .majorVersion(3)
                .minorVersion(0)
                .schemaDocument(schema)
                .build();
        postErrorStatusCode("/schemas", mapper.writeValueAsString(dto3), HttpStatus.BAD_REQUEST);
    }

    @Test
    void getActiveSchema_shouldReturnNotFound_whenNoSchemaExists() throws Exception {
        SubjectTypeDTO st = new SubjectTypeDTO("Battery", "EV Battery");
        postResponseAsObject("/admin/subject-types", mapper.writeValueAsString(st), SubjectTypeDTO.class);

        getErrorStatusCode("/schemas/Battery/current", HttpStatus.NOT_FOUND);
    }

    @Test
    void getExactSchema_shouldReturnNotFound_whenDoesNotExist() throws Exception {
        SubjectTypeDTO st = new SubjectTypeDTO("Battery", "EV Battery");
        postResponseAsObject("/admin/subject-types", mapper.writeValueAsString(st), SubjectTypeDTO.class);

        getErrorStatusCode("/schemas/Battery/1/0", HttpStatus.NOT_FOUND);
    }
}
