package ch.bfh.dpp_resolver.schemas;

import ch.bfh.dpp_resolver.ControllerTest;
import ch.bfh.dpp_resolver.admin.models.SubjectType;
import ch.bfh.dpp_resolver.admin.repositories.SubjectTypeRepository;
import ch.bfh.dpp_resolver.schemas.dtos.DppSchemaDTO;
import ch.bfh.dpp_resolver.schemas.repositories.DppSchemaRepository;
import ch.bfh.dpp_resolver.schemas.repositories.SchemaDependencyRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.result.MockMvcResultHandlers;

import java.util.Map;

import static org.hamcrest.Matchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class SchemaCycleIntegrationTest extends ControllerTest {

    @Autowired
    private SubjectTypeRepository subjectTypeRepository;

    @Autowired
    private DppSchemaRepository dppSchemaRepository;

    @Autowired
    private SchemaDependencyRepository schemaDependencyRepository;

    // Snake_case request bodies to match the Resolver's snake_case JSON contract.
    private final ObjectMapper jacksonMapper = new ObjectMapper()
            .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);

    @BeforeEach
    void cleanDb() {
        schemaDependencyRepository.deleteAllInBatch();
        dppSchemaRepository.deleteAllInBatch();
        subjectTypeRepository.deleteAllInBatch();

        createSubjectType("pv_module", "PV Module");
        createSubjectType("battery", "Battery");
        createSubjectType("inverter", "Inverter");
    }

    private void createSubjectType(String name, String description) {
        SubjectType st = new SubjectType();
        st.setName(name);
        st.setDescription(description);
        subjectTypeRepository.save(st);
    }

    @Test
    void testCyclePrevention() throws Exception {
        // 1. Publish battery 1.0 (no refs)
        DppSchemaDTO battery1 = DppSchemaDTO.builder()
                .subjectType("battery")
                .majorVersion(1)
                .minorVersion(0)
                .schemaDocument(Map.of("type", "object"))
                .build();

        mvc.perform(post("/schemas")
                .contentType(MediaType.APPLICATION_JSON)
                .content(jacksonMapper.writeValueAsString(battery1)))
                .andExpect(status().isCreated());

        // 2. Publish pv_module 1.0 referencing battery
        DppSchemaDTO pv1 = DppSchemaDTO.builder()
                .subjectType("pv_module")
                .majorVersion(1)
                .minorVersion(0)
                .schemaDocument(Map.of(
                        "type", "object",
                        "properties", Map.of(
                                "bat", Map.of("x-dpp-reference", "battery")
                        )
                ))
                .build();

        mvc.perform(post("/schemas")
                .contentType(MediaType.APPLICATION_JSON)
                .content(jacksonMapper.writeValueAsString(pv1)))
                .andExpect(status().isCreated());

        // 3. Attempt to publish battery 2.0 referencing pv_module -> CYCLE!
        DppSchemaDTO battery2 = DppSchemaDTO.builder()
                .subjectType("battery")
                .majorVersion(2)
                .minorVersion(0)
                .schemaDocument(Map.of(
                        "type", "object",
                        "properties", Map.of(
                                "pv", Map.of("x-dpp-reference", "pv_module")
                        )
                ))
                .build();

        mvc.perform(post("/schemas")
                .contentType(MediaType.APPLICATION_JSON)
                .content(jacksonMapper.writeValueAsString(battery2)))
                .andDo(MockMvcResultHandlers.print())
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.error", is("schema_cycle_detected")))
                .andExpect(jsonPath("$.cycle_path", contains("battery", "pv_module", "battery")));
    }

    @Test
    void testSelfReferenceDetection() throws Exception {
        DppSchemaDTO selfRef = DppSchemaDTO.builder()
                .subjectType("battery")
                .majorVersion(1)
                .minorVersion(0)
                .schemaDocument(Map.of(
                        "type", "object",
                        "properties", Map.of(
                                "self", Map.of("x-dpp-reference", "battery")
                        )
                ))
                .build();

        mvc.perform(post("/schemas")
                .contentType(MediaType.APPLICATION_JSON)
                .content(jacksonMapper.writeValueAsString(selfRef)))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.error", is("schema_self_reference")))
                .andExpect(jsonPath("$.subject_type", is("battery")));
    }

    @Test
    void testDiamondAcyclic() throws Exception {
        // A -> B, A -> C, B -> D, C -> D (DAG)
        createSubjectType("A", "A");
        createSubjectType("B", "B");
        createSubjectType("C", "C");
        createSubjectType("D", "D");

        publishSchema("D", 1, 0, Map.of());
        publishSchema("B", 1, 0, Map.of("d", Map.of("x-dpp-reference", "D")));
        publishSchema("C", 1, 0, Map.of("d", Map.of("x-dpp-reference", "D")));
        publishSchema("A", 1, 0, Map.of(
                "b", Map.of("x-dpp-reference", "B"),
                "c", Map.of("x-dpp-reference", "C")
        ));
        // All should succeed (201)
    }

    private void publishSchema(String type, int major, int minor, Map<String, Object> props) throws Exception {
        DppSchemaDTO dto = DppSchemaDTO.builder()
                .subjectType(type)
                .majorVersion(major)
                .minorVersion(minor)
                .schemaDocument(Map.of(
                        "type", "object",
                        "properties", props
                ))
                .build();

        mvc.perform(post("/schemas")
                .contentType(MediaType.APPLICATION_JSON)
                .content(jacksonMapper.writeValueAsString(dto)))
                .andExpect(status().isCreated());
    }
}
