package ch.bfh.dpp_resolver.url_resolver.services;

import ch.bfh.dpp_resolver.TestDatabaseCleaner;
import ch.bfh.dpp_resolver.admin.models.Platform;
import ch.bfh.dpp_resolver.admin.models.SubjectType;
import ch.bfh.dpp_resolver.admin.repositories.PlatformRepository;
import ch.bfh.dpp_resolver.admin.repositories.SubjectTypeRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@ActiveProfiles("test")
@Transactional
class UrlResolverServiceTest {

    @Autowired
    private PlatformRepository platformRepository;

    @Autowired
    private SubjectTypeRepository subjectTypeRepository;

    @Autowired
    private TestDatabaseCleaner databaseCleaner;

    @Autowired
    private UrlResolverService urlResolverService;

    private SubjectType subjectType;
    private Platform platform;

    @BeforeEach
    void setUp() {
        databaseCleaner.clean();

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

    @Test
    void resolveUrl_withValidInputs_shouldReturnCorrectUrl() {
        String resolvedUrl = urlResolverService.resolveUrl("Car", "ET-123");

        assertEquals("https://eurotax.com/res/Car/ET-123", resolvedUrl);
    }

    @Test
    void resolveUrl_withRevision_shouldReplaceMajorMinor() {
        platform.setResolutionUrl("https://eurotax.com/res/{subjectType}/{dppId}/{major}.{minor}");
        platformRepository.save(platform);

        String resolvedUrl = urlResolverService.resolveUrl("Car", "ET-123", "1.2");

        assertEquals("https://eurotax.com/res/Car/ET-123/1.2", resolvedUrl);
    }

    @Test
    void resolveUrl_withMajorOnly_shouldHandleMinorPlaceholder() {
        platform.setResolutionUrl("https://eurotax.com/res/{subjectType}/{dppId}/{major}.{minor}");
        platformRepository.save(platform);

        String resolvedUrl = urlResolverService.resolveUrl("Car", "ET-123", "1");

        assertFalse(resolvedUrl.contains("{minor}"), "Should not contain {minor} placeholder");
        assertEquals("https://eurotax.com/res/Car/ET-123/1", resolvedUrl);
    }

    @Test
    void resolveUrl_withRevision_shouldAppendIfNoPlaceholders() {
        platform.setResolutionUrl("https://eurotax.com/res/{subjectType}/{dppId}");
        platformRepository.save(platform);

        String resolvedUrl = urlResolverService.resolveUrl("Car", "ET-123", "1.2");

        assertEquals("https://eurotax.com/res/Car/ET-123/1.2", resolvedUrl);
    }

    @Test
    void resolveUrl_withInvalidDppId_shouldThrowException() {
        assertThrows(IllegalArgumentException.class, () -> urlResolverService.resolveUrl("Car", "invalid-id-format"));
    }

    @Test
    void resolveUrl_withInvalidRevisionFormat_shouldThrowException() {
        assertThrows(IllegalArgumentException.class, () -> urlResolverService.resolveUrl("Car", "ET-123", "1.2.3"));
    }

    @Test
    void resolveUrl_whenSubjectTypeNotSupportedByPlatform_shouldReturnNull() {
        Platform otherPlatform = new Platform();
        otherPlatform.setPlatformName("Other");
        otherPlatform.setAbbreviation("OT");
        otherPlatform.setResolutionUrl("https://other.com/res/{dppId}");
        otherPlatform.setSubjectTypes(List.of());
        platformRepository.save(otherPlatform);

        String resolvedUrl = urlResolverService.resolveUrl("Car", "OT-123");

        assertNull(resolvedUrl);
    }

    @Test
    void createUrl_missingDppIdPlaceholder_shouldThrowException() {
        platform.setResolutionUrl("https://eurotax.com/res/{subjectType}/");
        platformRepository.save(platform);

        assertThrows(IllegalArgumentException.class, () -> urlResolverService.resolveUrl("Car", "ET-123"));
    }
}
