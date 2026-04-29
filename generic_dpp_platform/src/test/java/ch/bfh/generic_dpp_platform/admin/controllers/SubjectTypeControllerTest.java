package ch.bfh.generic_dpp_platform.admin.controllers;

import ch.bfh.generic_dpp_platform.ControllerTest;
import ch.bfh.generic_dpp_platform.admin.dtos.SubjectTypeDTO;
import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;

import static org.junit.jupiter.api.Assertions.*;

public class SubjectTypeControllerTest extends ControllerTest {

    @Autowired
    private SubjectTypeRepository subjectTypeRepository;

    @AfterEach
    public void tearDown() {
        subjectTypeRepository.deleteAll();
    }

    @Test
    public void testGetAllSupportedSubjectTypes_HappyPath() throws Exception {
        SubjectTypeDTO[] response = getResponseAsObject("/admin/subject-types", SubjectTypeDTO[].class);
        assertNotNull(response);
        assertEquals(0, response.length);
    }

    @Test
    public void testCreateSubjectType_HappyPath() throws Exception {
        SubjectTypeDTO dto = SubjectTypeDTO.builder()
                .name("Battery")
                .description("Battery subject type")
                .build();

        String json = createGson(false).toJson(dto);

        SubjectTypeDTO response = postResponseAsObject("/admin/subject-types", json, SubjectTypeDTO.class);

        assertNotNull(response);
        assertEquals("Battery", response.getName());
        assertEquals("Battery subject type", response.getDescription());

        SubjectTypeDTO[] all = getResponseAsObject("/admin/subject-types", SubjectTypeDTO[].class);
        assertEquals(1, all.length);
        assertEquals("Battery", all[0].getName());
    }

    @Test
    public void testCreateSubjectType_DuplicateName_BadPath() throws Exception {
        SubjectTypeDTO dto = SubjectTypeDTO.builder()
                .name("Battery")
                .description("Battery subject type")
                .build();

        String json = createGson(false).toJson(dto);

        // First creation
        postResponseAsObject("/admin/subject-types", json, SubjectTypeDTO.class);

        // Second creation with same name
        postErrorStatusCode("/admin/subject-types", json, HttpStatus.BAD_REQUEST);
    }

    @Test
    public void testCreateSubjectType_EmptyBody_BadPath() throws Exception {
        postErrorStatusCode("/admin/subject-types", "", HttpStatus.BAD_REQUEST);
    }
}
