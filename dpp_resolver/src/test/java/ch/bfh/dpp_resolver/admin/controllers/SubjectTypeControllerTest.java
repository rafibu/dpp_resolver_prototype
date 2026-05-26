package ch.bfh.dpp_resolver.admin.controllers;

import ch.bfh.dpp_resolver.ControllerTest;
import ch.bfh.dpp_resolver.admin.dto.SubjectTypeDTO;
import ch.bfh.dpp_resolver.admin.repositories.SubjectTypeRepository;
import com.google.gson.Gson;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;

import static org.junit.jupiter.api.Assertions.*;

class SubjectTypeControllerTest extends ControllerTest {

    @Autowired
    private SubjectTypeRepository subjectTypeRepository;

    private final Gson gson = new Gson();

    @AfterEach
    void tearDown() {
        subjectTypeRepository.deleteAll();
    }

    @Test
    void getSubjectTypes_shouldReturnAllSubjectTypes() throws Exception {
        String url = "/admin/subject-types";

        // 1. Initial state: empty
        SubjectTypeDTO[] initial = getResponseAsObject(url, SubjectTypeDTO[].class);
        assertEquals(0, initial.length);

        // 2. Add some subject types
        SubjectTypeDTO type1 = new SubjectTypeDTO("Type1", "Desc1");
        SubjectTypeDTO type2 = new SubjectTypeDTO("Type2", "Desc2");

        postResponseAsObject(url, gson.toJson(type1), SubjectTypeDTO.class);
        postResponseAsObject(url, gson.toJson(type2), SubjectTypeDTO.class);

        // 3. Check if they are returned
        SubjectTypeDTO[] result = getResponseAsObject(url, SubjectTypeDTO[].class);
        assertEquals(2, result.length);

        boolean found1 = false;
        boolean found2 = false;
        for (SubjectTypeDTO dto : result) {
            if ("Type1".equals(dto.getName())) {
                assertEquals("Desc1", dto.getDescription());
                found1 = true;
            } else if ("Type2".equals(dto.getName())) {
                assertEquals("Desc2", dto.getDescription());
                found2 = true;
            }
        }
        assertTrue(found1);
        assertTrue(found2);
    }

    @Test
    void postSubjectType_shouldCreateNewSubjectType() throws Exception {
        String url = "/admin/subject-types";

        SubjectTypeDTO dto = new SubjectTypeDTO("NewSubjectType", "A new description");
        SubjectTypeDTO response = postResponseAsObject(url, gson.toJson(dto), SubjectTypeDTO.class);

        assertEquals(dto.getName(), response.getName());
        assertEquals(dto.getDescription(), response.getDescription());

        assertTrue(subjectTypeRepository.existsByName("NewSubjectType"));
    }

    @Test
    void postSubjectType_shouldReturnBadRequest_whenNameIsNull() throws Exception {
        String url = "/admin/subject-types";

        SubjectTypeDTO dto = new SubjectTypeDTO(null, "Description without name");
        postErrorStatusCode(url, gson.toJson(dto), HttpStatus.BAD_REQUEST);
    }

    @Test
    void postSubjectType_isIdempotent_whenAlreadyExists() throws Exception {
        String url = "/admin/subject-types";
        SubjectTypeDTO dto = new SubjectTypeDTO("Duplicate", "First");
        postResponseAsObject(url, gson.toJson(dto), SubjectTypeDTO.class);

        // Second call with same name should succeed (idempotent), not error
        SubjectTypeDTO duplicateDto = new SubjectTypeDTO("Duplicate", "Second");
        postResponseAsObject(url, gson.toJson(duplicateDto), SubjectTypeDTO.class);

        // Verify only one entry exists
        SubjectTypeDTO[] result = getResponseAsObject(url, SubjectTypeDTO[].class);
        long count = java.util.Arrays.stream(result).filter(t -> "Duplicate".equals(t.getName())).count();
        assertEquals(1, count);
    }
}
