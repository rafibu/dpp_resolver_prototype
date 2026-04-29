package ch.bfh.generic_dpp_platform.schemas.connectors;

import ch.bfh.generic_dpp_platform.admin.dtos.PlatformConfigDTO;
import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import ch.bfh.generic_dpp_platform.admin.services.PlatformConfigService;
import ch.bfh.generic_dpp_platform.schemas.DppSchemaRepository;
import ch.bfh.generic_dpp_platform.schemas.dtos.DppSchemaDTO;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchema;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchemaId;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.client.RestTemplate;

import java.util.Arrays;
import java.util.List;

/**
 *
 * @author rbu on 21.04.2026
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class ResolverConnector {

    private final PlatformConfigService configService;
    private final SubjectTypeRepository subjectTypeRepository;
    private final DppSchemaRepository dppSchemaRepository;
    private final RestTemplate restTemplate;

    private static final ObjectMapper MAPPER = new ObjectMapper().findAndRegisterModules();

    /**
     * Fetches and stores the latest schema for a given subject type.
     * @param subjectType The subject type to synchronize.
     */
    @Transactional
    public void syncSchema(String subjectType) {
        PlatformConfigDTO platformConfig = configService.getPlatformConfig();
        String resolverBaseUrl = platformConfig.getResolverBaseUrl();

        if (resolverBaseUrl == null || resolverBaseUrl.isBlank()) {
            throw new IllegalStateException("Resolver base URL is not configured");
        }

        SubjectType localSubjectType = subjectTypeRepository.findByName(subjectType)
                .orElseThrow(() -> new IllegalArgumentException("Subject type not found: " + subjectType));

        String url = resolverBaseUrl + "/schemas/" + subjectType;
        DppSchemaDTO[] remoteSchemas = restTemplate.getForObject(url, DppSchemaDTO[].class);

        if (remoteSchemas != null) {
            List<DppSchema> newSchemas = Arrays.stream(remoteSchemas)
                    .filter(dto -> {
                        DppSchemaId id = DppSchemaId.builder()
                                .subjectTypeId(localSubjectType.getId())
                                .majorVersion(dto.getMajorVersion())
                                .minorVersion(dto.getMinorVersion())
                                .build();
                        return !dppSchemaRepository.existsById(id);
                    })
                    .map(dto -> DppSchema.builder()
                            .id(DppSchemaId.builder()
                                    .subjectTypeId(localSubjectType.getId())
                                    .majorVersion(dto.getMajorVersion())
                                    .minorVersion(dto.getMinorVersion())
                                    .build())
                            .subjectType(localSubjectType)
                            .publishedAt(dto.getPublishedAt())
                            .schemaDocument(MAPPER.valueToTree(dto.getSchemaDocument()))
                            .build())
                    .toList();
            log.info("Found {} new schemas for subject type {}", newSchemas.size(), subjectType);
            dppSchemaRepository.saveAll(newSchemas);
        }
    }
}
