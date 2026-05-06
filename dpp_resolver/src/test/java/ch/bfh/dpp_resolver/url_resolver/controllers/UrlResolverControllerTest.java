package ch.bfh.dpp_resolver.url_resolver.controllers;

import ch.bfh.dpp_resolver.ControllerTest;
import ch.bfh.dpp_resolver.admin.models.Platform;
import ch.bfh.dpp_resolver.admin.models.SubjectType;
import ch.bfh.dpp_resolver.admin.repositories.PlatformRepository;
import ch.bfh.dpp_resolver.admin.repositories.SubjectTypeRepository;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;

import java.util.List;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class UrlResolverControllerTest extends ControllerTest {

    @Autowired
    private PlatformRepository platformRepository;

    @Autowired
    private SubjectTypeRepository subjectTypeRepository;

    private SubjectType subjectType;
    private Platform platform;

    @BeforeEach
    void setUp() {
        subjectType = new SubjectType();
        subjectType.setName("Car");
        subjectType = subjectTypeRepository.save(subjectType);

        platform = new Platform();
        platform.setPlatformName("EuroTax");
        platform.setAbbreviation("ET");
        platform.setResolutionUrl("https://eurotax.com/res/{subjectType}/{dppId}");
        platform.setSubjectTypes(List.of(subjectType));
        platform = platformRepository.save(platform);
    }

    @AfterEach
    void tearDown() {
        platformRepository.deleteAll();
        subjectTypeRepository.deleteAll();
    }

    @Test
    void resolveUrl_shouldRedirectToResolvedUrl() throws Exception {
        sendRequest(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get("/Car/ET-123"))
                .andExpect(status().isFound())
                .andExpect(header().string("Location", "https://eurotax.com/res/Car/ET-123"))
                .andExpect(header().string("X-DPP-Subject-Type", "Car"))
                .andExpect(header().string("X-DPP-Reference-Type", "SOFT"));
    }

    @Test
    void resolveUrlWithRevision_shouldRedirectToResolvedUrl() throws Exception {
        sendRequest(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get("/Car/ET-123/1.2"))
                .andExpect(status().isFound())
                .andExpect(header().string("Location", "https://eurotax.com/res/Car/ET-123/1.2"))
                .andExpect(header().string("X-DPP-Subject-Type", "Car"))
                .andExpect(header().string("X-DPP-Resolved-Revision", "1.2"))
                .andExpect(header().string("X-DPP-Reference-Type", "HARD"));
    }

    @Test
    void resolveUrl_shouldReturnNotFound_whenDppIdDoesNotExist() throws Exception {
        getErrorStatusCode("/Car/XX-123", HttpStatus.NOT_FOUND);
    }

    @Test
    void resolveUrl_shouldReturnBadRequest_whenDppIdFormatIsInvalid() throws Exception {
        getErrorStatusCode("/Car/invalidformat", HttpStatus.BAD_REQUEST);
    }

    @Test
    void resolveUrl_shouldReturnBadRequest_whenRevisionFormatIsInvalid() throws Exception {
        getErrorStatusCode("/Car/ET-123/1.2.3", HttpStatus.BAD_REQUEST);
    }
}
