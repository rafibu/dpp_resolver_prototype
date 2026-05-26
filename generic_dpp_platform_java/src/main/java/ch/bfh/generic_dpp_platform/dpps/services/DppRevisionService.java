package ch.bfh.generic_dpp_platform.dpps.services;

import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import ch.bfh.generic_dpp_platform.admin.services.PlatformConfigService;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppDetailDTO;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionRequestDTO;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionResponseDTO;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionSchemaDTO;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionSummaryDTO;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppSummaryDTO;
import ch.bfh.generic_dpp_platform.dpps.exceptions.DppAlreadyExistsException;
import ch.bfh.generic_dpp_platform.dpps.exceptions.DppReferenceResolutionException;
import ch.bfh.generic_dpp_platform.dpps.exceptions.DppRevisionConflictException;
import ch.bfh.generic_dpp_platform.dpps.models.*;
import ch.bfh.generic_dpp_platform.dpps.repositories.DppRevisionRepository;
import ch.bfh.generic_dpp_platform.dpps.repositories.LogicalDppRepository;
import ch.bfh.generic_dpp_platform.dpps.utils.DppReferenceExtractor;
import ch.bfh.generic_dpp_platform.dpps.utils.DppUtil;
import ch.bfh.generic_dpp_platform.schemas.connectors.ResolverConnector;
import ch.bfh.generic_dpp_platform.schemas.repositories.DppSchemaRepository;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchema;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchemaId;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.*;

/**
 *
 * @author rbu on 02.05.2026
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class DppRevisionService {

    private final LogicalDppRepository dppRepository;
    private final PlatformConfigService platformConfigService;
    private final SubjectTypeRepository subjectTypeRepository;
    private final DppSchemaRepository dppSchemaRepository;
    private final DppRevisionRepository dppRevisionRepository;
    private final DppReferenceExtractor referenceExtractor;
    private final DppRevisionCacheService cacheService;
    private final ResolverConnector resolverConnector;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Transactional(readOnly = true)
    public List<DppSummaryDTO> listAllDpps() {
        return dppRepository.findAll().stream().map(dpp -> {
            Optional<DppRevision> latest = dppRevisionRepository.findFirstByIdDppIdOrderByIdDppVersionDesc(dpp.getDppId());
            return DppSummaryDTO.builder()
                    .dppId(dpp.getDppId())
                    .subjectType(dpp.getSubjectType().getName())
                    .currentVersion(latest.map(DppRevision::getVersion).orElse(0))
                    .lastUpdated(latest.map(r -> r.getCreatedAt().toString()).orElse(dpp.getCreatedAt().toString()))
                    .build();
        }).toList();
    }

    @Transactional(readOnly = true)
    public DppDetailDTO getDppDetail(String dppId) {
        LogicalDpp dpp = dppRepository.findById(dppId)
                .orElseThrow(() -> new NoSuchElementException("DPP not found with ID: " + dppId));
        List<DppRevisionSummaryDTO> revisions = dppRevisionRepository
                .findAllByIdDppIdOrderByIdDppVersionAsc(dppId).stream()
                .map(DppRevisionService::toRevisionSummary)
                .toList();
        return DppDetailDTO.builder()
                .dppId(dppId)
                .subjectType(dpp.getSubjectType().getName())
                .revisions(revisions)
                .build();
    }

    @Transactional(readOnly = true)
    public DppRevisionResponseDTO getCurrentDppRevision(String dppId) {
        return getDppRevision(dppId, null);
    }

    @Transactional(readOnly = true)
    public DppRevisionResponseDTO getDppRevision(String dppId, Integer version) {
        if (dppId == null) {
            throw new IllegalArgumentException("DPP id must not be null");
        }

        if (!dppRepository.existsById(dppId)) {
            throw new NoSuchElementException("DPP not found with ID: " + dppId);
        }

        if (version == null) {
            DppRevision current = dppRevisionRepository.findFirstByIdDppIdOrderByIdDppVersionDesc(dppId)
                    .orElseThrow(() -> new NoSuchElementException("No revisions found for DPP ID: " + dppId));
            return toDTO(current);
        }

        DppRevision exactMatch = dppRevisionRepository.findById(new DppRevisionId(version, dppId))
                .orElseThrow(() -> new NoSuchElementException("Revision %d not found for DPP ID: %s".formatted(version, dppId)));
        return toDTO(exactMatch);
    }

    @Transactional
    public DppRevisionResponseDTO createNewDpp(DppRevisionRequestDTO requestDTO) {
        LogicalDpp dpp = new LogicalDpp();

        SubjectType subjectType = subjectTypeRepository.findByName(requestDTO.getSchemaVersion().getSubjectType())
                .orElseThrow(() -> new IllegalArgumentException("Subject type not found: " + requestDTO.getSchemaVersion().getSubjectType()));
        dpp.setSubjectType(subjectType);

        dpp.setCreatedAt(Instant.now());

        String dppId = requestDTO.getDppId();
        String issuerId = getIssuerId();

        if (dppId != null) {
            dppId = dppId.trim();
            if (!dppId.startsWith(issuerId)) {
                throw new IllegalArgumentException("DPP ID must start with issuer ID: " + issuerId);
            }
            if (dppRepository.existsById(dppId)) {
                throw new DppAlreadyExistsException("DPP already exists with ID: " + dppId);
            }
            dpp.setDppId(dppId);
        } else {
            dpp.setDppId(issuerId + "-" + UUID.randomUUID());
        }

        dpp = dppRepository.save(dpp);

        return createDppRevision(dpp, requestDTO);
    }

    @Transactional
    public DppRevisionResponseDTO createDppRevisionForExistingDpp(String dppId, DppRevisionRequestDTO requestDTO) {
        LogicalDpp dpp = dppRepository.findWithLockByDppId(dppId).orElseThrow();
        return createDppRevision(dpp, requestDTO);
    }


    private DppRevisionResponseDTO createDppRevision(LogicalDpp logicalDpp, DppRevisionRequestDTO requestDTO) {
        int nextRevisionNumber = checkAndGetNextVersionNumber(requestDTO.getVersion(), logicalDpp);

        DppSchema dppSchema = checkAndGetDppSchema(requestDTO.getSchemaVersion(), logicalDpp);

        Map<String, Object> validDppDocument = DppUtil.validateDppDocument(requestDTO.getDppPayload(), dppSchema);

        // 1. Extract references
        List<DppReference> references = referenceExtractor.extractReferences(objectMapper.valueToTree(validDppDocument));

        // 2. Resolve/Fetch/Cache hard references
        for (DppReference ref : references) {
            if (ref.type() == DppReference.DependencyType.HARD) {
                resolveAndCacheHardReference(ref);
            }
        }

        // 3. Bounded hard-cycle detection
        // Not needed anymore since Invariant 6 checks for cycles on schema level
        // cycleDetectionService.detectCycles(logicalDpp.getSubjectType().getName(), logicalDpp.getDppId(), nextRevisionNumber, validDppDocument);

        DppRevision newRevision = new DppRevision();
        newRevision.setId(new DppRevisionId(nextRevisionNumber, logicalDpp.getDppId()));
        newRevision.setDpp(logicalDpp);
        newRevision.setDppSchema(dppSchema);
        newRevision.setDppDocument(validDppDocument);
        newRevision.setCreatedAt(Instant.now());
        newRevision.setHashedDocument(DppUtil.hashDocument(validDppDocument));

        newRevision = dppRevisionRepository.save(newRevision);

        return toDTO(newRevision);
    }

    private void resolveAndCacheHardReference(DppReference ref) {
        String issuerId = getIssuerId();
        // Check if local
        if (ref.dppId().startsWith(issuerId)) {
            if (!dppRevisionRepository.existsById(new DppRevisionId(ref.version(), ref.dppId()))) {
                throw new DppReferenceResolutionException("Local hard reference not found: " + ref.originalRef(), ref.originalRef());
            }
            return;
        }

        // Check cache
        Optional<ReferencedDppRevision> cached = cacheService.getCachedRevision(ref.dppId(), ref.version());
        if (cached.isPresent()) {
            log.info("Using cached revision for hard reference: {}", ref.originalRef());
            return;
        }

        // Resolve via Resolver
        log.info("Resolving external hard reference: {}", ref.originalRef());
        DppRevisionResponseDTO resolved;
        try {
            resolved = resolverConnector.resolveDppRevision(ref.subjectType(), ref.dppId(), ref.version());
        } catch (DppReferenceResolutionException e) {
            // Ensure the unresolved reference is included in the exception for the API response
            if (e.getUnresolvedReference() == null) {
                throw new DppReferenceResolutionException(e.getMessage(), ref.originalRef());
            }
            throw e;
        }

        if (resolved == null) {
            throw new DppReferenceResolutionException("Resolver returned null for " + ref.originalRef(), ref.originalRef());
        }

        // Cache it
        ReferencedDppRevision external = ReferencedDppRevision.builder()
                .id(new ReferencedDppRevisionId(ref.dppId(), ref.version()))
                .subjectType(ref.subjectType())
                .schemaSubjectType(resolved.getSchemaVersion().getSubjectType())
                .schemaMajorVersion(resolved.getSchemaVersion().getMajorVersion())
                .schemaMinorVersion(resolved.getSchemaVersion().getMinorVersion())
                .dppDocument((Map<String, Object>) resolved.getDppPayload())
                .hashedDocument(DppUtil.hexToHash(resolved.getPayloadHash()))
                .fetchedAt(Instant.now())
                .build();
        cacheService.cacheRevision(external);
    }

    private DppSchema checkAndGetDppSchema(DppRevisionSchemaDTO schemaVersion, LogicalDpp logicalDpp) {
        if (schemaVersion == null) {
            throw new IllegalArgumentException("Schema version cannot be null");
        }
        if (!Objects.equals(schemaVersion.getSubjectType(), logicalDpp.getSubjectType().getName())) {
            throw new IllegalArgumentException("Schema version subject type %s does not match the DPP subject type %s".formatted(schemaVersion.getSubjectType(), logicalDpp.getSubjectType().getName()));
        }
        if (schemaVersion.getMajorVersion() == null || schemaVersion.getMinorVersion() == null) {
            throw new IllegalArgumentException("Schema version must contain major and minor version");
        }

        DppSchemaId schemaId = new DppSchemaId();
        schemaId.setMajorVersion(schemaVersion.getMajorVersion());
        schemaId.setMinorVersion(schemaVersion.getMinorVersion());
        schemaId.setSubjectTypeName(schemaVersion.getSubjectType());

        return dppSchemaRepository.findById(schemaId).orElseThrow(() -> new IllegalArgumentException("Schema version not found"));
    }

    private int checkAndGetNextVersionNumber(Integer version, LogicalDpp logicalDpp) {
        String dppId = logicalDpp.getDppId();
        Optional<DppRevision> latestRevision = dppRevisionRepository.findFirstByIdDppIdOrderByIdDppVersionDesc(dppId);

        if (latestRevision.isEmpty()) {
            if (version == null || version == 1) {
                return 1;
            }
            throw new DppRevisionConflictException("Version must be 1 if no revisions exist. Got: " + version);
        }

        int currentMaxVersion = latestRevision.get().getVersion();
        int nextVersion = currentMaxVersion + 1;
        if (version == null) {
            // No version specified, increment the current max version
            return nextVersion;
        }
        if (nextVersion != version) {
            throw new DppRevisionConflictException("Version conflict. Expected: %d, Got: %d".formatted(nextVersion, version));
        }
        return version;
    }


    private static DppRevisionSummaryDTO toRevisionSummary(DppRevision dppRevision) {
        String schemaRef = "%s/%d.%d".formatted(
                dppRevision.getDppSchema().getSubjectType().getName(),
                dppRevision.getDppSchema().getId().getMajorVersion(),
                dppRevision.getDppSchema().getId().getMinorVersion()
        );
        return DppRevisionSummaryDTO.builder()
                .version(dppRevision.getVersion())
                .schemaRef(schemaRef)
                .hash(DppUtil.hashToHex(dppRevision.getHashedDocument()))
                .timestamp(dppRevision.getCreatedAt().toString())
                .payload(dppRevision.getDppDocument())
                .build();
    }

    private static DppRevisionResponseDTO toDTO(DppRevision dppRevision) {
        return DppRevisionResponseDTO.builder()
                .dppId(dppRevision.getId().getDppId())
                .version(dppRevision.getVersion())
                .schemaVersion(toSchemaDTO(dppRevision.getDppSchema()))
                .dppPayload(dppRevision.getDppDocument())
                .payloadHash(DppUtil.hashToHex(dppRevision.getHashedDocument()))
                .createdAt(Date.from(dppRevision.getCreatedAt()))
                .build();
    }

    private static DppRevisionSchemaDTO toSchemaDTO(DppSchema schema) {
        return DppRevisionSchemaDTO.builder()
                .subjectType(schema.getSubjectType().getName())
                .majorVersion(schema.getId().getMajorVersion())
                .minorVersion(schema.getId().getMinorVersion())
                .build();
    }

    private String getIssuerId() {
        return platformConfigService.getPlatformConfig().getIssuerId();
    }
}
