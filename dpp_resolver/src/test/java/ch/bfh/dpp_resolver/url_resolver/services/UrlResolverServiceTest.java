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

    private Platform platform;

    @BeforeEach
    void setUp() {
        databaseCleaner.clean();

        SubjectType subjectType = new SubjectType();
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
    void resolveUrl_withIntegerRevision_shouldAppendRevisionAsPathSegment() {
        String resolvedUrl = urlResolverService.resolveUrl("Car", "ET-123", "2");

        assertEquals("https://eurotax.com/res/Car/ET-123/2", resolvedUrl);
    }

    @Test
    void resolveUrl_withRevisionPlaceholder_shouldSubstituteRevision() {
        platform.setResolutionUrl("https://eurotax.com/res/{subjectType}/{dppId}/{revision}");
        platformRepository.save(platform);

        String resolvedUrl = urlResolverService.resolveUrl("Car", "ET-123", "3");

        assertEquals("https://eurotax.com/res/Car/ET-123/3", resolvedUrl);
    }

    @Test
    void resolveUrl_withMultiDashDppId_shouldExtractIssuerFromFirstSegment() {
        // DPP IDs can have multiple dashes; only the first segment is the issuer.
        // e.g. issuerA-550e8400-e29b-41d4-a716-446655440000 (issuer UUID format)
        String resolvedUrl = urlResolverService.resolveUrl("Car", "ET-item-with-dashes");

        assertEquals("https://eurotax.com/res/Car/ET-item-with-dashes", resolvedUrl);
    }

    @Test
    void resolveUrl_withNoDashInDppId_shouldThrowException() {
        // A DPP ID with no dash has no issuer prefix, which is invalid.
        assertThrows(IllegalArgumentException.class, () -> urlResolverService.resolveUrl("Car", "invalidformat"));
    }

    @Test
    void resolveUrl_withNonIntegerRevision_shouldThrowException() {
        assertThrows(IllegalArgumentException.class, () -> urlResolverService.resolveUrl("Car", "ET-123", "abc"));
    }

    @Test
    void resolveUrl_withZeroRevision_shouldThrowException() {
        assertThrows(IllegalArgumentException.class, () -> urlResolverService.resolveUrl("Car", "ET-123", "0"));
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
    void resolveUrl_whenIssuerNotRegistered_shouldReturnNull() {
        String resolvedUrl = urlResolverService.resolveUrl("Car", "UNKNOWN-123");

        assertNull(resolvedUrl);
    }

    @Test
    void buildUrl_missingDppIdPlaceholder_shouldThrowException() {
        platform.setResolutionUrl("https://eurotax.com/res/{subjectType}/");
        platformRepository.save(platform);

        assertThrows(IllegalArgumentException.class, () -> urlResolverService.resolveUrl("Car", "ET-123"));
    }
}
