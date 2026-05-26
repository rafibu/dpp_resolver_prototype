package ch.bfh.generic_dpp_platform.dpps.services;

import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import ch.bfh.generic_dpp_platform.admin.services.PlatformConfigService;
import ch.bfh.generic_dpp_platform.dpps.dtos.*;
import ch.bfh.generic_dpp_platform.dpps.exceptions.DppAlreadyExistsException;
import ch.bfh.generic_dpp_platform.dpps.exceptions.DppReferenceResolutionException;
import ch.bfh.generic_dpp_platform.dpps.exceptions.DppRevisionConflictException;
import ch.bfh.generic_dpp_platform.dpps.models.*;
import ch.bfh.generic_dpp_platform.dpps.repositories.DppRevisionRepository;
import ch.bfh.generic_dpp_platform.dpps.repositories.LogicalDppRepository;
import ch.bfh.generic_dpp_platform.dpps.utils.DppReferenceExtractor;
import ch.bfh.generic_dpp_platform.dpps.utils.DppUtil;
import ch.bfh.generic_dpp_platform.schemas.connectors.ResolverConnector;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchema;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchemaId;
import ch.bfh.generic_dpp_platform.schemas.repositories.DppSchemaRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.*;

/**
 * Service implementing the DPP-platform-side lifecycle operations for logical DPPs and their revisions.
 * <p>
 * This service realizes the platform operations {@code issue} and {@code revise} from the transition system.
 * It creates logical DPPs, appends immutable revisions, validates payloads against pinned cached schemas,
 * computes payload hashes, and checks hard-reference resolvability before a revision is committed.
 * </p>
 * <p>
 * Resolver-side operations such as schema publication, issuer registration, migration, compatibility checking,
 * and schema-dependency graph acyclicity are intentionally not implemented here. This service assumes that
 * schemas loaded into the platform cache originate from the resolver and that the resolver enforces its own
 * preconditions.
 * </p>
 * <p>
 * The implementation maps the formal issuer-qualified logical DPP identity to a single persisted identifier
 * using the convention {@code issuerId + "-" + localId}. This preserves issuer scoping while avoiding global
 * platform-local identifier collisions.
 * </p>
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

    /**
     * Separator used to encode the formal logical DPP identity into a single platform identifier.
     * <p>
     * The formal model identifies a logical DPP by an issuer-qualified identity. In this implementation,
     * that identity is encoded as {@code issuerId + "-" + localId}. The delimiter check avoids accepting
     * accidental prefix matches such as issuer {@code abc} accepting an ID owned by issuer {@code abcd}.
     * </p>
     */
    private static final String DPP_ID_ISSUER_SEPARATOR = "-";

    @Transactional(readOnly = true)
    public List<DppSummaryDTO> listAllDpps() {
        return dppRepository.findAll().stream().map(dpp -> {
            Optional<DppRevision> latest = dppRevisionRepository.findFirstByIdDppIdOrderByIdDppVersionDesc(dpp.getDppId());
            return DppSummaryDTO.builder()
                    .dppId(dpp.getDppId())
                    .subjectType(dpp.getSubjectType().getName())
                    .currentVersion(latest.map(DppRevision::getVersion).orElse(0))
                    .lastUpdated(latest.map(r -> r.getCreatedAt().toString()).orElse(null))
                    .build();
        }).toList();
    }

    /**
     * Returns a logical DPP with all locally stored revisions ordered by ascending version number.
     *
     * @param dppId the issuer-qualified DPP identifier
     * @return the DPP details including revision summaries
     * @throws NoSuchElementException if no logical DPP with the given identifier exists locally
     */
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

    /**
     * Returns the current revision of a logical DPP.
     * <p>
     * The current revision is the revision with the highest version number for the given DPP.
     * This corresponds to the current-revision derived notion in the formal model.
     * </p>
     *
     * @param dppId the issuer-qualified DPP identifier
     * @return the current revision DTO
     * @throws IllegalArgumentException if {@code dppId} is null
     * @throws NoSuchElementException   if the DPP or its revisions do not exist locally
     */
    @Transactional(readOnly = true)
    public DppRevisionResponseDTO getCurrentDppRevision(String dppId) {
        return getDppRevision(dppId, null);
    }

    /**
     * Returns either the current revision or a specific revision of a logical DPP.
     * <p>
     * If {@code version} is null, the method returns the current revision, defined as the revision with the
     * highest version number. If {@code version} is present, the method returns exactly that immutable revision.
     * This endpoint is used both by local clients and by other platforms after resolver indirection.
     * </p>
     *
     * @param dppId   the issuer-qualified DPP identifier
     * @param version the requested revision version, or null to request the current revision
     * @return the requested DPP revision DTO
     * @throws IllegalArgumentException if {@code dppId} is null
     * @throws NoSuchElementException   if the DPP or requested revision does not exist locally
     */
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

    /**
     * Issues a new logical DPP and creates its first immutable revision.
     * <p>
     * This method implements the platform-side {@code issue} operation. It ensures that the DPP identifier is
     * owned by this platform's configured issuer, rejects duplicate logical DPPs, creates the logical DPP record,
     * and delegates revision creation to {@link #createDppRevision(LogicalDpp, DppRevisionRequestDTO)}.
     * </p>
     * <p>
     * If the request does not provide a DPP identifier, a new issuer-qualified identifier is generated using
     * the convention {@code issuerId + "-" + UUID}.
     * </p>
     *
     * @param requestDTO the request containing the schema version, payload, optional DPP ID, and optional version
     * @return the created first revision
     * @throws IllegalArgumentException  if the subject type is unknown or the supplied DPP ID is not owned by
     *                                   this platform's issuer
     * @throws DppAlreadyExistsException if a logical DPP with the supplied identifier already exists
     */
    @Transactional
    public DppRevisionResponseDTO issueDpp(DppRevisionRequestDTO requestDTO) {
        LogicalDpp dpp = new LogicalDpp();

        SubjectType subjectType = subjectTypeRepository.findByName(requestDTO.getSchemaVersion().getSubjectType())
                .orElseThrow(() -> new IllegalArgumentException("Subject type not found: " + requestDTO.getSchemaVersion().getSubjectType()));
        dpp.setSubjectType(subjectType);

        String dppId = requestDTO.getDppId();
        String issuerId = getIssuerId();

        if (dppId != null) {
            dppId = dppId.trim();
            validateDppIdOwnedByIssuer(dppId, issuerId);
            if (dppRepository.existsById(dppId)) {
                throw new DppAlreadyExistsException("DPP already exists with ID: " + dppId);
            }
            dpp.setDppId(dppId);
        } else {
            dpp.setDppId(generateDppId(issuerId));
        }

        dpp = dppRepository.save(dpp);

        return createDppRevision(dpp, requestDTO);
    }

    /**
     * Appends a new immutable revision to an existing logical DPP.
     * <p>
     * This method implements the platform-side {@code revise} operation. It obtains a pessimistic lock on the
     * logical DPP before computing the next version number, preventing concurrent revise requests from assigning
     * the same version.
     * </p>
     *
     * @param dppId      the issuer-qualified DPP identifier of the logical DPP to revise
     * @param requestDTO the revision request containing the schema version, payload, and optional version
     * @return the newly created revision
     * @throws NoSuchElementException         if the logical DPP does not exist
     * @throws DppRevisionConflictException   if the requested version is not the next consecutive version
     * @throws IllegalArgumentException       if schema or payload validation fails
     * @throws DppReferenceResolutionException if a hard reference cannot be resolved
     */
    @Transactional
    public DppRevisionResponseDTO reviseExistingDpp(String dppId, DppRevisionRequestDTO requestDTO) {
        LogicalDpp dpp = dppRepository.findWithLockByDppId(dppId).orElseThrow();
        return createDppRevision(dpp, requestDTO);
    }

    /**
     * Creates and persists a new immutable revision for a logical DPP.
     * <p>
     * This method contains the shared revision-creation logic for both {@code issue} and {@code revise}.
     * It enforces the platform-local parts of the formal model:
     * </p>
     * <ul>
     *     <li>I2 by assigning or checking the next consecutive version number,</li>
     *     <li>I3 by requiring an explicit cached schema version,</li>
     *     <li>I4 by hashing the validated payload before persistence.</li>
     *     <li>I5 by validating the payload against the pinned schema,</li>
     *     <li>I7 by resolving all hard references before committing,</li>
     * </ul>
     * <p>
     * Soft references are extracted but not resolved, because unresolved soft references do not invalidate the
     * revision in the formal model.
     * </p>
     *
     * @param logicalDpp the logical DPP to which the new revision belongs
     * @param requestDTO the revision request
     * @return the persisted revision converted to an API DTO
     */
    private DppRevisionResponseDTO createDppRevision(LogicalDpp logicalDpp, DppRevisionRequestDTO requestDTO) {
        int nextRevisionNumber = checkAndGetNextVersionNumber(requestDTO.getVersion(), logicalDpp);

        //Check for Invariant 3 (Schema explicitness)
        DppSchema dppSchema = checkAndGetDppSchema(requestDTO.getSchemaVersion(), logicalDpp);

        //Check for Invariant 5 (Schema conformance)
        Map<String, Object> validDppDocument = DppUtil.validateDppDocument(requestDTO.getDppPayload(), dppSchema);

        // 1. Extract references
        List<DppReference> references = referenceExtractor.extractReferences(objectMapper.valueToTree(validDppDocument));

        /*
         * 2. Resolve, fetch, and cache hard references.
         *
         * Soft references are intentionally ignored here. In the formal model, a soft reference identifies
         * only a logical DPP and may resolve dynamically to its current revision. It is informational and
         * does not contribute to the hard-dependency closure required for compliance. Therefore, unresolved
         * soft references do not invalidate the revision being issued or revised.
         *
         * Hard references, name a concrete revision version and must resolve before the new
         * revision is committed. This operationalizes invariant I7 (hard resolvability).
         */
        for (DppReference ref : references) {
            if (ref.type() == DppReference.DependencyType.HARD) {
                resolveAndCacheHardReference(ref);
            }
        }

        // 3. The hard-cycle detection is done on the federated resolver level when creating the schemas. Therefore, this cycle detection is not needed here. But we left it in to show an alternative approach.

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

    /**
     * Verifies that a hard reference resolves to an existing concrete revision.
     * <p>
     * Local references are checked directly against this platform's revision repository. External references are
     * first looked up in the local reference cache. If absent, the resolver is used to locate and fetch the target
     * revision from the currently hosting platform; the fetched revision is then cached locally.
     * </p>
     * <p>
     * This method operationalizes invariant I7 for hard references. It is not used for soft references.
     * </p>
     *
     * @param ref the hard reference to resolve
     * @throws DppReferenceResolutionException if the target revision cannot be found locally, resolved through
     *                                         the resolver, fetched from the target platform, or cached
     */
    private void resolveAndCacheHardReference(DppReference ref) {
        String issuerId = getIssuerId();
        // Check if local
        if (isDppIdOwnedByIssuer(ref.dppId(), issuerId)) {
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

    /**
     * This method operationalizes Invariant 3 (Schema explicitness).
     * Because I3 is on the federated level, we might need to re-fetch new schemas from the federated resolver.
     * <br>
     * Validates the provided schema version and retrieves the corresponding DppSchema.
     *
     * @param schemaVersion the schema version to validate and retrieve. Must not be null and should have
     *                      valid major and minor versions. The subject type must match the subject type
     *                      of the provided logicalDpp.
     * @param logicalDpp    the logical DPP whose subject type must match that of the schema version.
     * @return the DppSchema corresponding to the provided schemaVersion.
     * @throws IllegalArgumentException if the schemaVersion is null, does not contain valid major and minor
     *                                  versions, the subject type does not match, or the schema version is
     *                                  not found in the repository.
     */
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

        Optional<DppSchema> cachedSchema = dppSchemaRepository.findById(schemaId);
        if (cachedSchema.isPresent()) {
            return cachedSchema.get();
        }

        log.info(
                "Schema version {}/{}.{} not found in local cache. Synchronizing schemas from resolver.",
                schemaVersion.getSubjectType(),
                schemaVersion.getMajorVersion(),
                schemaVersion.getMinorVersion()
        );
        resolverConnector.cacheSchema(schemaVersion.getSubjectType());

        return dppSchemaRepository.findById(schemaId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Schema version not found after resolver synchronization: %s/%d.%d".formatted(
                                schemaVersion.getSubjectType(),
                                schemaVersion.getMajorVersion(),
                                schemaVersion.getMinorVersion()
                        )
                ));
    }

    /**
     * Checks the specified version number against the latest revision of the given logical DPP
     * and determines the next valid version number. If no version is provided, the method
     * increments the latest version number. If a version conflict is detected, an exception is thrown.
     * This operationalizes Invariant 2 "Version monotonicity and density"
     *
     * @param version    the requested version number. Can be null, in which case the next version
     *                   is automatically determined based on the current maximum version.
     * @param logicalDpp the logical DPP object whose version is being checked and updated.
     *                   This object contains the DPP identifier used to fetch revision details.
     * @return the next valid version number based on the provided input and latest revision data.
     * @throws DppRevisionConflictException if the provided version conflicts with the expected next version.
     */
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

    private String generateDppId(String issuerId) {
        return issuerId + DPP_ID_ISSUER_SEPARATOR + UUID.randomUUID();
    }

    private boolean isDppIdOwnedByIssuer(String dppId, String issuerId) {
        return dppId != null && dppId.startsWith(issuerId + DPP_ID_ISSUER_SEPARATOR);
    }

    private void validateDppIdOwnedByIssuer(String dppId, String issuerId) {
        if (!isDppIdOwnedByIssuer(dppId, issuerId)) {
            throw new IllegalArgumentException(
                    "DPP ID must start with issuer ID followed by '%s': %s%s"
                            .formatted(DPP_ID_ISSUER_SEPARATOR, issuerId, DPP_ID_ISSUER_SEPARATOR)
            );
        }
    }
}
