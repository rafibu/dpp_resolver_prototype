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
import com.fasterxml.jackson.core.type.TypeReference;
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
    private static final int DIRECT_REVISION_RESOLUTION_DEPTH = 1;
    private static final int MAX_CLOSURE_DEPTH = 10;

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
     * This method preserves the direct revision response contract: callers receive only the requested revision,
     * not the transitive hard-reference closure. It still routes through the shared resolution logic with
     * {@code maxDepth = 1}; callers that need the bounded closure should use
     * {@link #getDppRevisionClosure(String, Integer, Integer)}.
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
        return resolveDppRevision(
                dppId,
                version,
                DppRevisionResolutionOptions.direct()
        ).rootRevision();
    }

    /**
     * Returns a bounded hard-reference closure rooted at a specific revision of a locally hosted DPP.
     * <p>
     * Closure resolution returns the root revision plus unique hard-reference dependencies reached by recursively
     * traversing payload references up to {@code maxDepth}. A depth of {@code 1} includes only direct hard
     * references; a depth of {@code 2} also includes hard references of those directly referenced revisions.
     * Soft references are not traversed. The traversal is intended for validation, audit, offline caching, and
     * benchmark scenarios where clients need a deterministic bounded dependency set.
     * </p>
     *
     * @param dppId    the issuer-qualified DPP identifier
     * @param version  the concrete revision version
     * @param maxDepth positive traversal depth, bounded to {@value #MAX_CLOSURE_DEPTH}
     * @return the root revision and the resolved hard-reference closure entries
     * @throws IllegalArgumentException        if {@code dppId} is null or {@code maxDepth} is invalid
     * @throws NoSuchElementException          if the root DPP or revision does not exist locally
     * @throws DppReferenceResolutionException if a hard reference in the bounded closure cannot be resolved
     */
    @Transactional
    public DppRevisionClosureResponseDTO getDppRevisionClosure(String dppId, Integer version, Integer maxDepth) {
        DppRevisionResolutionOptions options = DppRevisionResolutionOptions.closure(maxDepth);
        return resolveDppRevision(dppId, version, options).toClosureDTO();
    }

    private DppRevisionResolutionResult resolveDppRevision(String dppId,
                                                          Integer version,
                                                          DppRevisionResolutionOptions options) {
        DppRevisionResponseDTO rootRevision = loadStoredDppRevision(dppId, version);

        if (!options.expandClosure()) {
            return new DppRevisionResolutionResult(rootRevision, List.of());
        }

        LinkedHashMap<RevisionKey, DppRevisionResponseDTO> resolvedRevisions = new LinkedHashMap<>();
        Set<RevisionKey> visited = new HashSet<>();
        Deque<TraversalItem> queue = new ArrayDeque<>();

        visited.add(RevisionKey.from(rootRevision));
        queue.addLast(new TraversalItem(rootRevision, 0));

        while (!queue.isEmpty()) {
            TraversalItem current = queue.removeFirst();
            if (current.depth() >= options.maxDepth()) {
                continue;
            }

            for (DppReference ref : extractSortedHardReferences(current.revision())) {
                RevisionKey key = RevisionKey.from(ref);
                if (!visited.add(key)) {
                    continue;
                }

                DppRevisionResponseDTO resolved = resolveHardReference(ref);
                resolvedRevisions.put(key, resolved);
                queue.addLast(new TraversalItem(resolved, current.depth() + 1));
            }
        }

        return new DppRevisionResolutionResult(rootRevision, List.copyOf(resolvedRevisions.values()));
    }

    private DppRevisionResponseDTO loadStoredDppRevision(String dppId, Integer version) {
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

    private List<DppReference> extractSortedHardReferences(DppRevisionResponseDTO revision) {
        return referenceExtractor.extractReferences(objectMapper.valueToTree(revision.getDppPayload())).stream()
                .filter(ref -> ref.type() == DppReference.DependencyType.HARD)
                .sorted(Comparator
                        .comparing(DppReference::subjectType, Comparator.nullsFirst(String::compareTo))
                        .thenComparing(DppReference::dppId, Comparator.nullsFirst(String::compareTo))
                        .thenComparing(DppReference::version, Comparator.nullsFirst(Integer::compareTo))
                        .thenComparing(DppReference::jsonPath, Comparator.nullsFirst(String::compareTo)))
                .toList();
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
     * Persist a copied immutable revision during an administrative issuer-migration import.
     * <p>
     * This is not an alternative to {@link #issueDpp(DppRevisionRequestDTO)} or
     * {@link #reviseExistingDpp(String, DppRevisionRequestDTO)}. It is the DPP-service part of a migration
     * workflow where another already-authoritative platform has issued revisions and a successor platform must
     * serve the same immutable artefacts after resolver routing moves to it.
     * </p>
     * <p>
     * The method deliberately reuses the same persisted entities and invariant checks as normal revision
     * creation where they apply:
     * </p>
     * <ul>
     *     <li>the logical DPP record is created or reused in {@link LogicalDppRepository},</li>
     *     <li>the payload is validated against the exact cached schema (I5),</li>
     *     <li>the supplied payload hash is recomputed and verified before persistence (I4),</li>
     *     <li>an already imported revision is returned unchanged, preserving idempotent migration retries.</li>
     * </ul>
     * <p>
     * Hard references are not resolved here because the imported revision has already been issued elsewhere.
     * The successor platform is copying a historical artefact byte-for-byte; changing dependency resolution at
     * import time would make migration a new issue/revise transition, which is precisely what this endpoint
     * avoids.
     * </p>
     *
     * @param revisionDTO copied revision DTO received through the administrative import endpoint
     * @param subjectType already registered subject type for the imported logical DPP
     * @param schema      exact cached schema referenced by the imported revision
     * @return the stored revision DTO, or the existing stored revision when the import is retried
     * @throws IllegalArgumentException if identifiers are missing, subject types conflict, schema references do
     *                                  not match, or the supplied hash does not match the payload
     */
    @Transactional
    public DppRevisionResponseDTO importExistingRevision(
            DppRevisionResponseDTO revisionDTO,
            SubjectType subjectType,
            DppSchema schema
    ) {
        validateImportedRevisionEnvelope(revisionDTO, subjectType, schema);

        LogicalDpp logicalDpp = dppRepository.findById(revisionDTO.getDppId()).orElseGet(() -> {
            LogicalDpp created = new LogicalDpp();
            created.setDppId(revisionDTO.getDppId());
            created.setSubjectType(subjectType);
            return dppRepository.save(created);
        });
        if (!logicalDpp.getSubjectType().getName().equals(subjectType.getName())) {
            throw new IllegalArgumentException("Imported revisions for one DPP must use one subject type");
        }

        DppRevisionId revisionId = new DppRevisionId(revisionDTO.getVersion(), revisionDTO.getDppId());
        Optional<DppRevision> existing = dppRevisionRepository.findById(revisionId);
        if (existing.isPresent()) {
            return toDTO(existing.get());
        }

        Map<String, Object> payload = DppUtil.validateDppDocument(revisionDTO.getDppPayload(), schema);
        String computedHash = DppUtil.hashToHex(DppUtil.hashDocument(payload));
        if (!computedHash.equals(revisionDTO.getPayloadHash())) {
            throw new IllegalArgumentException("Imported revision payload hash mismatch for " + revisionDTO.getDppId());
        }

        DppRevision revision = new DppRevision();
        revision.setId(revisionId);
        revision.setDpp(logicalDpp);
        revision.setDppSchema(schema);
        revision.setDppDocument(payload);
        revision.setHashedDocument(DppUtil.hexToHash(revisionDTO.getPayloadHash()));
        revision.setCreatedAt(revisionDTO.getCreatedAt() != null ? revisionDTO.getCreatedAt().toInstant() : Instant.now());

        return toDTO(dppRevisionRepository.save(revision));
    }

    private void validateImportedRevisionEnvelope(
            DppRevisionResponseDTO revisionDTO,
            SubjectType subjectType,
            DppSchema schema
    ) {
        if (revisionDTO.getDppId() == null || revisionDTO.getDppId().isBlank()) {
            throw new IllegalArgumentException("dpp_id is required for imported revisions");
        }
        if (revisionDTO.getVersion() == null || revisionDTO.getVersion() < 1) {
            throw new IllegalArgumentException("version must be positive for imported revisions");
        }
        DppRevisionSchemaDTO schemaVersion = revisionDTO.getSchemaVersion();
        if (schemaVersion == null) {
            throw new IllegalArgumentException("schema_version is required for imported revisions");
        }
        if (revisionDTO.getPayloadHash() == null || revisionDTO.getPayloadHash().isBlank()) {
            throw new IllegalArgumentException("payload_hash is required for imported revisions");
        }
        if (!Objects.equals(schemaVersion.getSubjectType(), subjectType.getName())) {
            throw new IllegalArgumentException("Imported revision subject type does not match registered subject type");
        }
        DppSchemaId schemaId = schema.getId();
        if (!Objects.equals(schemaVersion.getSubjectType(), schemaId.getSubjectTypeName())
                || !Objects.equals(schemaVersion.getMajorVersion(), schemaId.getMajorVersion())
                || !Objects.equals(schemaVersion.getMinorVersion(), schemaId.getMinorVersion())) {
            throw new IllegalArgumentException("Imported revision schema_version does not match cached schema");
        }
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
                resolveHardReference(ref);
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
     * Resolves a hard reference to an existing concrete revision and caches external results.
     * <p>
     * Local references are checked directly against this platform's revision repository. External references are
     * first looked up in the local reference cache. If absent, the resolver is used to locate and fetch the target
     * revision from the currently hosting platform; the fetched revision is then cached locally.
     * </p>
     * <p>
     * This method operationalizes invariant I7 for hard references and is shared by revision creation and bounded
     * closure traversal. It is not used for soft references.
     * </p>
     *
     * @param ref the hard reference to resolve
     * @return the resolved revision DTO
     * @throws DppReferenceResolutionException if the target revision cannot be found locally, resolved through
     *                                         the resolver, fetched from the target platform, or cached
     */
    private DppRevisionResponseDTO resolveHardReference(DppReference ref) {
        String issuerId = getIssuerId();
        // Check if local
        if (isDppIdOwnedByIssuer(ref.dppId(), issuerId)) {
            DppRevision revision = dppRevisionRepository.findById(new DppRevisionId(ref.version(), ref.dppId()))
                    .orElseThrow(() -> new DppReferenceResolutionException(
                            "Local hard reference not found: " + ref.originalRef(),
                            ref.originalRef()
                    ));
            return toDTO(revision);
        }

        // Check cache
        Optional<ReferencedDppRevision> cached = cacheService.getCachedRevision(ref.dppId(), ref.version());
        if (cached.isPresent()) {
            log.info("Using cached revision for hard reference: {}", ref.originalRef());
            return toDTO(cached.get());
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

        cacheResolvedExternalRevision(ref, resolved);
        return resolved;
    }

    private void cacheResolvedExternalRevision(DppReference ref, DppRevisionResponseDTO resolved) {
        ReferencedDppRevision external = ReferencedDppRevision.builder()
                .id(new ReferencedDppRevisionId(ref.dppId(), ref.version()))
                .subjectType(ref.subjectType())
                .schemaSubjectType(resolved.getSchemaVersion().getSubjectType())
                .schemaMajorVersion(resolved.getSchemaVersion().getMajorVersion())
                .schemaMinorVersion(resolved.getSchemaVersion().getMinorVersion())
                .dppDocument(toPayloadMap(resolved.getDppPayload()))
                .hashedDocument(DppUtil.hexToHash(resolved.getPayloadHash()))
                .createdAt(resolved.getCreatedAt() != null ? resolved.getCreatedAt().toInstant() : null)
                .fetchedAt(Instant.now())
                .build();
        cacheService.cacheRevision(external);
    }

    private Map<String, Object> toPayloadMap(Object payload) {
        return objectMapper.convertValue(payload, new TypeReference<>() {
        });
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

    private static DppRevisionResponseDTO toDTO(ReferencedDppRevision dppRevision) {
        return DppRevisionResponseDTO.builder()
                .dppId(dppRevision.getDppId())
                .version(dppRevision.getDppVersion())
                .schemaVersion(DppRevisionSchemaDTO.builder()
                        .subjectType(dppRevision.getSchemaSubjectType())
                        .majorVersion(dppRevision.getSchemaMajorVersion())
                        .minorVersion(dppRevision.getSchemaMinorVersion())
                        .build())
                .dppPayload(dppRevision.getDppDocument())
                .payloadHash(DppUtil.hashToHex(dppRevision.getHashedDocument()))
                .createdAt(dppRevision.getCreatedAt() != null ? Date.from(dppRevision.getCreatedAt()) : null)
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

    private record DppRevisionResolutionOptions(int maxDepth, boolean expandClosure) {
        private static DppRevisionResolutionOptions direct() {
            return new DppRevisionResolutionOptions(DIRECT_REVISION_RESOLUTION_DEPTH, false);
        }

        private static DppRevisionResolutionOptions closure(Integer maxDepth) {
            if (maxDepth == null) {
                maxDepth = MAX_CLOSURE_DEPTH;
            }
            if (maxDepth < 1 || maxDepth > MAX_CLOSURE_DEPTH) {
                throw new IllegalArgumentException("max_depth must be between 1 and " + MAX_CLOSURE_DEPTH);
            }
            return new DppRevisionResolutionOptions(maxDepth, true);
        }
    }

    private record DppRevisionResolutionResult(DppRevisionResponseDTO rootRevision,
                                               List<DppRevisionResponseDTO> resolvedRevisions) {
        private DppRevisionClosureResponseDTO toClosureDTO() {
            return DppRevisionClosureResponseDTO.builder()
                    .rootRevision(rootRevision)
                    .resolvedRevisions(resolvedRevisions)
                    .build();
        }
    }

    private record TraversalItem(DppRevisionResponseDTO revision, int depth) {
    }

    private record RevisionKey(String dppId, Integer version) {
        private static RevisionKey from(DppRevisionResponseDTO revision) {
            return new RevisionKey(revision.getDppId(), revision.getVersion());
        }

        private static RevisionKey from(DppReference ref) {
            return new RevisionKey(ref.dppId(), ref.version());
        }
    }
}
