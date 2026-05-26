package ch.bfh.generic_dpp_platform.schemas.connectors;

import ch.bfh.generic_dpp_platform.admin.dtos.PlatformConfigDTO;
import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import ch.bfh.generic_dpp_platform.admin.services.PlatformConfigService;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionResponseDTO;
import ch.bfh.generic_dpp_platform.dpps.exceptions.DppReferenceResolutionException;
import ch.bfh.generic_dpp_platform.schemas.dtos.DppSchemaDTO;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchema;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchemaId;
import ch.bfh.generic_dpp_platform.schemas.repositories.DppSchemaRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestTemplate;

import java.net.URI;
import java.util.Arrays;
import java.util.List;

/**
 * This class is responsible for interacting with the Resolver service
 * to synchronize schema data, resolve DPP revisions, and resolve DPP revision URLs.
 * It communicates with external services using HTTP requests.
 *
 * @author rbu on 20.04.2026
 */
@Slf4j
@Component
public class ResolverConnector {

    private final PlatformConfigService configService;
    private final SubjectTypeRepository subjectTypeRepository;
    private final DppSchemaRepository dppSchemaRepository;
    private final RestTemplate restTemplate;
    private final RestTemplate noRedirectRestTemplate;

    public ResolverConnector(
            PlatformConfigService configService,
            SubjectTypeRepository subjectTypeRepository,
            DppSchemaRepository dppSchemaRepository,
            RestTemplate restTemplate,
            @Qualifier("noRedirectRestTemplate") RestTemplate noRedirectRestTemplate) {
        this.configService = configService;
        this.subjectTypeRepository = subjectTypeRepository;
        this.dppSchemaRepository = dppSchemaRepository;
        this.restTemplate = restTemplate;
        this.noRedirectRestTemplate = noRedirectRestTemplate;
    }

    private static final ObjectMapper MAPPER = new ObjectMapper().findAndRegisterModules();

    /**
     * Fetches and stores the latest schema for a given subject type.
     * The method works as is explained in the operation system (Section 5).
     * @param subjectType The subject type to synchronize.
     */
    @Transactional
    public void cacheSchema(String subjectType) {
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
                                .subjectTypeName(localSubjectType.getName())
                                .majorVersion(dto.getMajorVersion())
                                .minorVersion(dto.getMinorVersion())
                                .build();
                        return !dppSchemaRepository.existsById(id);
                    })
                    .map(dto -> DppSchema.builder()
                            .id(DppSchemaId.builder()
                                    .subjectTypeName(localSubjectType.getName())
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

    /**
     * Resolves a DPP revision through the Resolver.
     *
     * @param subjectType The subject type of the DPP.
     * @param dppId       The federated ID of the DPP.
     * @param version     The specific version to resolve (must be present for hard references).
     * @return The resolved DppRevisionResponseDTO.
     * @throws DppReferenceResolutionException if resolution or fetching fails.
     */
    public DppRevisionResponseDTO resolveDppRevision(String subjectType, String dppId, Integer version) {
        if (version == null) {
            throw new IllegalArgumentException("Version must be present for hard reference resolution");
        }

        URI resolveUrl = resolveDppRevisionUrl(subjectType, dppId, version);
        log.info("Fetching resolved DPP revision from: {}", resolveUrl);

        try {
            ResponseEntity<DppRevisionResponseDTO> response = restTemplate.getForEntity(resolveUrl, DppRevisionResponseDTO.class);
            if (response.getStatusCode().is2xxSuccessful() && response.getBody() != null) {
                return response.getBody();
            } else {
                throw new DppReferenceResolutionException("Failed to fetch resolved DPP revision from %s. Status: %s".formatted(resolveUrl, response.getStatusCode()));
            }
        } catch (HttpClientErrorException e) {
            if (e.getStatusCode() == HttpStatus.NOT_FOUND) {
                throw new DppReferenceResolutionException("DPP revision %s/%d not found at resolved URL %s".formatted(dppId, version, resolveUrl));
            }
            throw new DppReferenceResolutionException("Error fetching resolved DPP revision from %s: %s".formatted(resolveUrl, e.getMessage()));
        } catch (Exception e) {
            throw new DppReferenceResolutionException("Unexpected error fetching resolved DPP revision from %s: %s".formatted(resolveUrl, e.getMessage()));
        }
    }

    /**
     * Resolves the URL of a DPP revision through the Resolver using GET and 302 Location.
     *
     * @param subjectType The subject type of the DPP.
     * @param dppId       The federated ID of the DPP.
     * @param version     The version.
     * @return The resolved URI from the Location header.
     * @throws DppReferenceResolutionException if resolution fails.
     */
    public URI resolveDppRevisionUrl(String subjectType, String dppId, Integer version) {
        PlatformConfigDTO platformConfig = configService.getPlatformConfig();
        String resolverBaseUrl = platformConfig.getResolverBaseUrl();

        if (resolverBaseUrl == null || resolverBaseUrl.isBlank()) {
            throw new IllegalStateException("Resolver base URL is not configured");
        }

        if (version == null) {
            throw new IllegalArgumentException("Version must be present for hard reference resolution");
        }

        String resolverPath = "/%s/%s/%d".formatted(subjectType, dppId, version);
        String url = resolverBaseUrl + resolverPath;

        log.info("Resolving DPP reference through Resolver GET: {}", url);

        try {
            // Use non-redirecting RestTemplate to capture the 302 Location
            ResponseEntity<Void> response = noRedirectRestTemplate.exchange(url, HttpMethod.GET, null, Void.class);

            if (response.getStatusCode() == HttpStatus.FOUND || response.getStatusCode() == HttpStatus.MOVED_PERMANENTLY || response.getStatusCode().is3xxRedirection()) {
                URI location = response.getHeaders().getLocation();
                if (location == null) {
                    throw new DppReferenceResolutionException("Resolver returned %s without Location header for %s".formatted(response.getStatusCode(), url));
                }
                return location;
            }

            if (response.getStatusCode().is2xxSuccessful()) {
                throw new DppReferenceResolutionException("Resolver returned 200 OK instead of redirect for %s. Expected 302 Found.".formatted(url));
            }

            throw new DppReferenceResolutionException("Unexpected status from Resolver for %s: %s".formatted(url, response.getStatusCode()));

        } catch (HttpClientErrorException e) {
            if (e.getStatusCode() == HttpStatus.NOT_FOUND) {
                throw new DppReferenceResolutionException("DPP revision %s/%d not found in Resolver".formatted(dppId, version));
            }
            if (e.getStatusCode() == HttpStatus.BAD_REQUEST) {
                throw new DppReferenceResolutionException("Malformed reference for Resolver: " + e.getResponseBodyAsString());
            }
            throw new DppReferenceResolutionException("Error resolving DPP reference through Resolver: " + e.getMessage());
        } catch (DppReferenceResolutionException e) {
            throw e;
        } catch (Exception e) {
            throw new DppReferenceResolutionException("Unexpected error resolving DPP reference: " + e.getMessage());
        }
    }
}
