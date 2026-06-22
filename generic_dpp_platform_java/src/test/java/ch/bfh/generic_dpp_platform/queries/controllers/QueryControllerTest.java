package ch.bfh.generic_dpp_platform.queries.controllers;

import ch.bfh.generic_dpp_platform.ControllerTest;
import ch.bfh.generic_dpp_platform.admin.dtos.SubjectTypeDTO;
import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionRequestDTO;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionResponseDTO;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionSchemaDTO;
import ch.bfh.generic_dpp_platform.queries.dtos.QueryExecutionMode;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchema;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchemaId;
import ch.bfh.generic_dpp_platform.schemas.repositories.DppSchemaRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.Parameter;
import org.junit.jupiter.params.ParameterizedClass;
import org.junit.jupiter.params.provider.EnumSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import java.time.Instant;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ParameterizedClass(name = "[{index}] {0}")
@EnumSource(value = QueryExecutionMode.class, names = {"ON_DEMAND", "INDEXED"})
class QueryControllerTest extends ControllerTest {

    private static final String ISSUER_ID = "issuerA";
    private static final String SUBJECT_TYPE = "Battery";
    private static final String UNKNOWN_SUBJECT_TYPE = "UnknownSubjectType";

    @Autowired
    private SubjectTypeRepository subjectTypeRepository;

    @Autowired
    private DppSchemaRepository dppSchemaRepository;

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Parameter(0)
    private QueryExecutionMode executionMode;

    @BeforeEach
    void setupData() throws Exception {
        registerSubjectType(SUBJECT_TYPE);
    }

    private void registerSubjectType(String name) throws Exception {
        SubjectTypeDTO subjectType = SubjectTypeDTO.builder()
                .name(name)
                .description(name + " subject type")
                .build();
        postResponseAsObject("/admin/subject-types", createGson(false).toJson(subjectType), SubjectTypeDTO.class);

        SubjectType subjectTypeEntity = subjectTypeRepository.findByName(name).orElseThrow();
        DppSchemaId schemaId = DppSchemaId.builder()
                .subjectTypeName(name)
                .majorVersion(1)
                .minorVersion(0)
                .build();
        DppSchema schema = DppSchema.builder()
                .id(schemaId)
                .subjectType(subjectTypeEntity)
                .schemaDocument(objectMapper.readTree("{}"))
                .publishedAt(Instant.now())
                .build();
        dppSchemaRepository.save(schema);
    }

    @Test
    void selectWithoutFilters_shouldReturnAllCurrentRevisionDocuments() throws Exception {
        seedBatteryDpps();

        JsonNode response = query(baseQuery("SELECT"));

        assertEquals("SELECT", response.path("result_mode").asText());
        assertEquals(executionMode.name(), response.path("execution_mode").asText());
        JsonNode matches = response.path("matches");
        assertTrue(matches.isArray());
        assertEquals(5, matches.size());
        assertEquals(Set.of("Battery A", "Battery B", "Battery C", "Battery D", "Battery E"), names(matches));
        assertFalse(names(matches).contains("Battery A old"));
        assertFalse(names(matches).contains("Battery B old"));
    }

    @Test
    void countWithoutFilters_shouldCountAllCurrentRevisions() throws Exception {
        seedBatteryDpps();

        assertCount(query(baseQuery("COUNT")), 5);
    }

    @Test
    void operatorEq_shouldMatchExactValue() throws Exception {
        seedBatteryDpps();

        assertCount(query(filter(baseQuery("COUNT"), 0, "chemistry", "EQ", "NMC")), 3);
    }

    @Test
    void operatorNeq_shouldExcludeExactValue() throws Exception {
        seedBatteryDpps();

        assertCount(query(filter(baseQuery("COUNT"), 0, "chemistry", "NEQ", "NMC")), 2);
    }

    @Test
    void operatorExists_shouldMatchDocumentsWithPath() throws Exception {
        seedBatteryDpps();

        assertCount(query(filter(baseQuery("COUNT"), 0, "manufacturer.country", "EXISTS", null)), 4);
    }

    @Test
    void operatorNotExists_shouldMatchDocumentsWithoutPath() throws Exception {
        seedBatteryDpps();

        assertCount(query(filter(baseQuery("COUNT"), 0, "manufacturer.country", "NOT_EXISTS", null)), 1);
    }

    @Test
    void operatorIn_shouldMatchAnyListedValue() throws Exception {
        seedBatteryDpps();

        MockHttpServletRequestBuilder request = filter(baseQuery("COUNT"), 0, "chemistry", "IN", null)
                .param("filters[0].value", "NMC", "LFP");

        assertCount(query(request), 4);
    }

    @Test
    void operatorGt_shouldMatchGreaterThan() throws Exception {
        seedBatteryDpps();

        MockHttpServletRequestBuilder request = filter(baseQuery("COUNT"), 0, "weight_kg", "EXISTS", null);
        filter(request, 1, "weight_kg", "GT", "400");

        assertCount(query(request), 2);
    }

    @Test
    void operatorGte_shouldMatchGreaterThanOrEqual() throws Exception {
        seedBatteryDpps();

        MockHttpServletRequestBuilder request = filter(baseQuery("COUNT"), 0, "weight_kg", "EXISTS", null);
        filter(request, 1, "weight_kg", "GTE", "410");

        assertCount(query(request), 2);
    }

    @Test
    void operatorLt_shouldMatchLessThan() throws Exception {
        seedBatteryDpps();

        MockHttpServletRequestBuilder request = filter(baseQuery("COUNT"), 0, "weight_kg", "EXISTS", null);
        filter(request, 1, "weight_kg", "LT", "350");

        assertCount(query(request), 1);
    }

    @Test
    void operatorLte_shouldMatchLessThanOrEqual() throws Exception {
        seedBatteryDpps();

        MockHttpServletRequestBuilder request = filter(baseQuery("COUNT"), 0, "weight_kg", "EXISTS", null);
        filter(request, 1, "weight_kg", "LTE", "350");

        assertCount(query(request), 2);
    }

    @Test
    void nestedPathFilter_shouldResolveNestedMap() throws Exception {
        seedBatteryDpps();

        assertCount(query(filter(baseQuery("COUNT"), 0, "manufacturer.country", "EQ", "CH")), 2);
    }

    @Test
    void combinedFilters_shouldApplyAndSemantics() throws Exception {
        seedBatteryDpps();

        MockHttpServletRequestBuilder countRequest = filter(baseQuery("COUNT"), 0, "chemistry", "EQ", "NMC");
        filter(countRequest, 1, "manufacturer.country", "EQ", "CH");
        filter(countRequest, 2, "recyclable", "EQ", "true");
        assertCount(query(countRequest), 1);

        MockHttpServletRequestBuilder selectRequest = filter(baseQuery("SELECT"), 0, "chemistry", "EQ", "NMC");
        filter(selectRequest, 1, "manufacturer.country", "EQ", "CH");
        filter(selectRequest, 2, "recyclable", "EQ", "true");
        JsonNode matches = query(selectRequest).path("matches");
        assertEquals(1, matches.size());
        assertEquals("Battery A", matches.get(0).path("name").asText());
        assertEquals("A-001", matches.get(0).path("serial").asText());
    }

    @Test
    void selectWithReturnFields_shouldReturnOnlyRequestedFields() throws Exception {
        seedBatteryDpps();

        MockHttpServletRequestBuilder request = filter(baseQuery("SELECT"), 0, "serial", "EQ", "A-001")
                .param("returnFields", "name", "capacity_kwh", "manufacturer.country");
        JsonNode matches = query(request).path("matches");

        assertEquals(1, matches.size());
        JsonNode match = matches.get(0);
        assertEquals("Battery A", match.path("name").asText());
        assertEquals(55, match.path("capacity_kwh").asInt());
        assertEquals("CH", match.path("manufacturer.country").asText());
        assertFalse(match.has("serial"));
        assertFalse(match.has("chemistry"));
        assertFalse(match.has("weight_kg"));
    }

    @Test
    void sumWithoutFilters_shouldSumNumericAggregatePath() throws Exception {
        seedBatteryDpps();

        assertAggregate(query(baseQuery("SUM").param("aggregatePath", "weight_kg")), 1580.0);
    }

    @Test
    void sumWithFilters_shouldSumOnlyMatchingDocuments() throws Exception {
        seedBatteryDpps();

        MockHttpServletRequestBuilder request = filter(baseQuery("SUM"), 0, "recyclable", "EQ", "true")
                .param("aggregatePath", "weight_kg");
        assertAggregate(query(request), 820.0);
    }

    @Test
    void unknownSubjectType_select_shouldReturnEmptyMatches() throws Exception {
        JsonNode response = query(baseQuery("SELECT").param("subjectType", UNKNOWN_SUBJECT_TYPE));

        assertTrue(response.path("matches").isArray());
        assertEquals(0, response.path("matches").size());
        assertTrue(response.path("count").isMissingNode() || response.path("count").isNull());
        assertTrue(response.path("aggregate").isMissingNode() || response.path("aggregate").isNull());
        assertNotNull(response.path("platform_id").asText());
    }

    @Test
    void unknownSubjectType_count_shouldReturnZero() throws Exception {
        assertCount(query(baseQuery("COUNT").param("subjectType", UNKNOWN_SUBJECT_TYPE)), 0);
    }

    @Test
    void unknownSubjectType_sum_shouldReturnZero() throws Exception {
        assertAggregate(query(baseQuery("SUM").param("subjectType", UNKNOWN_SUBJECT_TYPE).param("aggregatePath", "something")), 0.0);
    }

    @Test
    void missingPathWithEq_shouldNotCrashAndShouldReturnNoMatches() throws Exception {
        seedBatteryDpps();

        assertCount(query(filter(baseQuery("COUNT"), 0, "does.not.exist", "EQ", "anything")), 0);
    }

    @Test
    void missingPathWithExists_shouldReturnNoMatches() throws Exception {
        seedBatteryDpps();

        assertCount(query(filter(baseQuery("COUNT"), 0, "does.not.exist", "EXISTS", null)), 0);
    }

    @Test
    void missingPathWithNotExists_shouldReturnAllCurrentDocuments() throws Exception {
        seedBatteryDpps();

        assertCount(query(filter(baseQuery("COUNT"), 0, "does.not.exist", "NOT_EXISTS", null)), 5);
    }

    @Test
    void missingPathWithComparison_shouldReturnBadRequest() throws Exception {
        seedBatteryDpps();

        sendRequest(filter(baseQuery("COUNT"), 0, "does.not.exist", "GT", "10"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void sumWithMissingAggregatePath_shouldIgnoreMissingValues() throws Exception {
        seedBatteryDpps();

        MockHttpServletRequestBuilder request = filter(baseQuery("SUM"), 0, "serial", "EQ", "D-001")
                .param("aggregatePath", "metrics.soh");
        assertAggregate(query(request), 0.0);
    }

    @Test
    void sumWithNonNumericAggregateValue_shouldReturnBadRequest() throws Exception {
        seedBatteryDpps();

        MockHttpServletRequestBuilder request = filter(baseQuery("SUM"), 0, "serial", "EQ", "E-001")
                .param("aggregatePath", "capacity_kwh");
        sendRequest(request).andExpect(status().isBadRequest());
    }

    @Test
    void sumWithoutAggregatePath_shouldReturnBadRequest() throws Exception {
        seedBatteryDpps();

        sendRequest(baseQuery("SUM")).andExpect(status().isBadRequest());
    }

    @Test
    void traverse_happyPath_oneSubjectOnePath_shouldReturnMatches() throws Exception {
        seedBatteryDpps();
        seedTraverseData();

        MockHttpServletRequestBuilder request = baseTraverseQuery(SUBJECT_TYPE, ISSUER_ID + "-battery-1");
        addSource(request, 0, "Vehicle", "battery");

        JsonNode response = query(request);
        assertEquals(1, response.path("matches").size());
        assertEquals("Car 1", response.path("matches").get(0).path("name").asText());
    }

    @Test
    void traverse_happyPath_noMatches_shouldReturnEmptyList() throws Exception {
        seedBatteryDpps();
        seedTraverseData();

        // Query for Battery B references in Vehicle battery path (none exist, Battery B is battery-2)
        MockHttpServletRequestBuilder request = baseTraverseQuery(SUBJECT_TYPE, ISSUER_ID + "-battery-2");
        addSource(request, 0, "Vehicle", "battery");

        JsonNode response = query(request);
        assertEquals(0, response.path("matches").size());
    }

    @Test
    void traverse_happyPath_multiSubjectMultiPath_shouldReturnAllMatches() throws Exception {
        seedBatteryDpps();
        seedTraverseData();

        // Seed another subject type "Drone" referencing Battery A
        registerSubjectType("Drone");
        issue(ISSUER_ID + "-drone-1", "Drone", Map.of(
                "name", "Drone 1",
                "power_source", Map.of("$ref", SUBJECT_TYPE + "/" + ISSUER_ID + "-battery-1")
        ));

        MockHttpServletRequestBuilder request = baseTraverseQuery(SUBJECT_TYPE, ISSUER_ID + "-battery-1");
        addSource(request, 0, "Vehicle", "battery", "other_reference");
        addSource(request, 1, "Drone", "power_source");

        JsonNode response = query(request);
        assertEquals(3, response.path("matches").size());
        Set<String> names = names(response.path("matches"));
        assertTrue(names.contains("Car 1"));
        assertTrue(names.contains("Car 2"));
        assertTrue(names.contains("Drone 1"));
    }

    @Test
    void traverse_happyPath_unknownSubject_shouldReturnEmptyList() throws Exception {
        seedBatteryDpps();

        MockHttpServletRequestBuilder request = baseTraverseQuery(SUBJECT_TYPE, ISSUER_ID + "-battery-1");
        addSource(request, 0, UNKNOWN_SUBJECT_TYPE);

        JsonNode response = query(request);
        assertEquals(0, response.path("matches").size());
    }

    @Test
    void traverse_badPath_malformed_shouldReturnBadRequest() throws Exception {
        // Missing dppId
        sendRequest(get("/query/traverse")
                .param("subjectType", SUBJECT_TYPE)
                .param("sources[0].subjectType", "Vehicle"))
                .andExpect(status().isBadRequest());

        // Missing subjectType
        sendRequest(get("/query/traverse")
                .param("dppId", "some-id")
                .param("sources[0].subjectType", "Vehicle"))
                .andExpect(status().isBadRequest());

        // Missing sources
        sendRequest(get("/query/traverse")
                .param("subjectType", SUBJECT_TYPE)
                .param("dppId", "some-id"))
                .andExpect(status().isBadRequest());
    }

    private MockHttpServletRequestBuilder baseTraverseQuery(String targetSubjectType, String targetDppId) {
        return get("/query/traverse")
                .param("subjectType", targetSubjectType)
                .param("dppId", targetDppId)
                .param("executionMode", executionMode.name());
    }

    private MockHttpServletRequestBuilder addSource(MockHttpServletRequestBuilder request, int index, String subjectType, String... referencePaths) {
        request.param("sources[" + index + "].subjectType", subjectType);
        for (int i = 0; i < referencePaths.length; i++) {
            request.param("sources[" + index + "].referencePaths[" + i + "]", referencePaths[i]);
        }
        return request;
    }

    private void seedTraverseData() throws Exception {
        registerSubjectType("Vehicle");

        // Issue a vehicle referencing Battery A (ISSUER_ID + "-battery-1")
        issue(ISSUER_ID + "-vehicle-1", "Vehicle", Map.of(
                "name", "Car 1",
                "battery", Map.of("$ref", SUBJECT_TYPE + "/" + ISSUER_ID + "-battery-1")
        ));

        // Issue another vehicle referencing Battery A but in a different path
        issue(ISSUER_ID + "-vehicle-2", "Vehicle", Map.of(
                "name", "Car 2",
                "other_reference", Map.of("$ref", SUBJECT_TYPE + "/" + ISSUER_ID + "-battery-1")
        ));
    }

    private MockHttpServletRequestBuilder baseQuery(String resultMode) {
        return get("/query/predicate")
                .param("resultMode", resultMode)
                .param("executionMode", executionMode.name())
                .param("subjectType", SUBJECT_TYPE);
    }

    private MockHttpServletRequestBuilder filter(MockHttpServletRequestBuilder request, int index, String path,
                                                 String operator, String value) {
        request.param("filters[" + index + "].path", path)
                .param("filters[" + index + "].operator", operator);
        if (value != null) {
            request.param("filters[" + index + "].value", value);
        }
        return request;
    }

    private JsonNode query(MockHttpServletRequestBuilder request) throws Exception {
        String response = sendRequest(request)
                .andExpect(status().isOk())
                .andReturn()
                .getResponse()
                .getContentAsString();
        return objectMapper.readTree(response);
    }

    private void assertCount(JsonNode response, long expected) {
        assertEquals("COUNT", response.path("result_mode").asText());
        assertEquals(executionMode.name(), response.path("execution_mode").asText());
        assertEquals(expected, response.path("count").asLong());
        assertTrue(response.path("aggregate").isMissingNode() || response.path("aggregate").isNull());
        assertTrue(response.path("matches").isMissingNode() || response.path("matches").isNull());
    }

    private void assertAggregate(JsonNode response, double expected) {
        assertEquals("SUM", response.path("result_mode").asText());
        assertEquals(executionMode.name(), response.path("execution_mode").asText());
        assertEquals(expected, response.path("aggregate").asDouble(), 0.0001);
        assertTrue(response.path("count").isMissingNode() || response.path("count").isNull());
        assertTrue(response.path("matches").isMissingNode() || response.path("matches").isNull());
    }

    private Set<String> names(JsonNode matches) {
        Set<String> result = new HashSet<>();
        for (JsonNode match : matches) {
            result.add(match.path("name").asText());
        }
        return result;
    }

    private void seedBatteryDpps() throws Exception {
        issue(ISSUER_ID + "-battery-1", batteryARevision1());
        revise(ISSUER_ID + "-battery-1", 2, batteryARevision2());
        issue(ISSUER_ID + "-battery-2", batteryBRevision1());
        revise(ISSUER_ID + "-battery-2", 2, batteryBRevision2());
        issue(ISSUER_ID + "-battery-3", batteryCRevision1());
        issue(ISSUER_ID + "-battery-4", batteryDRevision1());
        issue(ISSUER_ID + "-battery-5", batteryERevision1());
    }

    private DppRevisionResponseDTO issue(String dppId, Map<String, Object> payload) throws Exception {
        return issue(dppId, SUBJECT_TYPE, payload);
    }

    private DppRevisionResponseDTO issue(String dppId, String subjectType, Map<String, Object> payload) throws Exception {
        return postResponseAsObject("/dpps/issue", createGson(false).toJson(revisionRequest(dppId, subjectType, 1, payload)),
                DppRevisionResponseDTO.class);
    }

    private DppRevisionResponseDTO revise(String dppId, int version, Map<String, Object> payload) throws Exception {
        return postResponseAsObject("/dpps/" + dppId + "/revise", createGson(false).toJson(revisionRequest(null, SUBJECT_TYPE, version, payload)),
                DppRevisionResponseDTO.class);
    }

    private DppRevisionRequestDTO revisionRequest(String dppId, String subjectType, int version, Map<String, Object> payload) {
        return DppRevisionRequestDTO.builder()
                .dppId(dppId)
                .version(version)
                .schemaVersion(DppRevisionSchemaDTO.builder()
                        .subjectType(subjectType)
                        .majorVersion(1)
                        .minorVersion(0)
                        .build())
                .dppPayload(payload)
                .build();
    }

    private Map<String, Object> batteryARevision1() {
        return Map.of(
                "name", "Battery A old", "serial", "A-OLD", "chemistry", "LFP", "capacity_kwh", 45,
                "weight_kg", 300, "recyclable", true,
                "manufacturer", Map.of("name", "OldMaker", "country", "DE"),
                "metrics", Map.of("soh", 0.91, "cycles", 100));
    }

    private Map<String, Object> batteryARevision2() {
        return Map.of(
                "name", "Battery A", "serial", "A-001", "chemistry", "NMC", "capacity_kwh", 55,
                "weight_kg", 320, "recyclable", true,
                "manufacturer", Map.of("name", "Acme", "country", "CH"),
                "metrics", Map.of("soh", 0.95, "cycles", 120));
    }

    private Map<String, Object> batteryBRevision1() {
        return Map.of(
                "name", "Battery B old", "serial", "B-OLD", "chemistry", "NMC", "capacity_kwh", 60,
                "weight_kg", 380, "recyclable", false,
                "manufacturer", Map.of("name", "Other", "country", "DE"),
                "metrics", Map.of("soh", 0.80, "cycles", 400));
    }

    private Map<String, Object> batteryBRevision2() {
        return Map.of(
                "name", "Battery B", "serial", "B-001", "chemistry", "LFP", "capacity_kwh", 75,
                "weight_kg", 410, "recyclable", false,
                "manufacturer", Map.of("name", "Globex", "country", "DE"),
                "metrics", Map.of("soh", 0.88, "cycles", 260));
    }

    private Map<String, Object> batteryCRevision1() {
        return Map.of(
                "name", "Battery C", "serial", "C-001", "chemistry", "NMC", "capacity_kwh", 95,
                "weight_kg", 500, "recyclable", true,
                "manufacturer", Map.of("name", "Acme", "country", "US"),
                "metrics", Map.of("soh", 0.99, "cycles", 20));
    }

    private Map<String, Object> batteryDRevision1() {
        return Map.of(
                "name", "Battery D", "serial", "D-001", "chemistry", "LTO", "capacity_kwh", 30,
                "recyclable", true,
                "manufacturer", Map.of("name", "MissingWeightInc"),
                "metrics", Map.of("cycles", 5));
    }

    private Map<String, Object> batteryERevision1() {
        return Map.of(
                "name", "Battery E", "serial", "E-001", "chemistry", "NMC", "capacity_kwh", "not-a-number",
                "weight_kg", 350, "recyclable", false,
                "manufacturer", Map.of("name", "BadData", "country", "CH"),
                "metrics", Map.of("soh", "bad-soh", "cycles", 15));
    }
}
