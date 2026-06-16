package ch.bfh.generic_dpp_platform.admin.services;

import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionResponseDTO;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionSchemaDTO;
import ch.bfh.generic_dpp_platform.dpps.models.ReferencedDppRevision;
import ch.bfh.generic_dpp_platform.dpps.repositories.DppRevisionRepository;
import ch.bfh.generic_dpp_platform.dpps.repositories.LogicalDppRepository;
import ch.bfh.generic_dpp_platform.dpps.repositories.ReferencedDppRevisionRepository;
import ch.bfh.generic_dpp_platform.dpps.services.DppRevisionService;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchema;
import ch.bfh.generic_dpp_platform.schemas.services.DppSchemaService;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Comparator;
import java.util.List;

/**
 * Service for administrative platform operations.
 * <p>
 * Administrative endpoints are scenario and operator helpers around the normal platform model. They should not
 * introduce a parallel path for DPP semantics. This service therefore coordinates existing subject-type, schema,
 * and DPP revision services whenever an administrative operation needs to touch DPP data.
 * </p>
 */
@Service
@RequiredArgsConstructor
public class AdminService {

    private final ReferencedDppRevisionRepository cacheRepository;
    private final DppRevisionRepository revisionRepository;
    private final LogicalDppRepository logicalDppRepository;
    private final SubjectTypeService subjectTypeService;
    private final DppSchemaService schemaService;
    private final DppRevisionService revisionService;

    /**
     * Return the platform-local cache of externally resolved hard-reference targets.
     * <p>
     * This cache is populated by the normal DPP revision service when issue/revise or closure traversal resolves
     * hard references hosted on other platforms.
     * </p>
     *
     * @return cached external revisions currently stored by this platform
     */
    @Transactional(readOnly = true)
    public List<ReferencedDppRevision> getCache() {
        return cacheRepository.findAll();
    }

    /**
     * Clear scenario data while keeping platform configuration, subject types, and cached schemas intact.
     * <p>
     * Scenario runners use this helper to get a clean DPP state between runs. Resolver/platform registration and
     * schema availability are deliberately left untouched because they are configured through their own paths.
     * </p>
     */
    @Transactional
    public void resetPlatformData() {
        cacheRepository.deleteAll();
        revisionRepository.deleteAll();
        logicalDppRepository.deleteAll();
    }

    /**
     * Import immutable revisions copied from a previous hosting platform during issuer migration.
     * <p>
     * The import endpoint is used by Scenario S1 after resolver routing has moved an issuer to a successor
     * platform. It is not an issue/revise operation: the revisions already exist and already carry hashes. This
     * method simply verifies that the successor platform knows the referenced subject type and schema, then asks
     * the DPP revision service to persist the same revision artefacts.
     * </p>
     * <p>
     * Revisions are processed in DPP/version order so imports of multiple versions of one logical DPP are
     * deterministic. Re-running the same import is idempotent because the DPP service returns existing revisions
     * unchanged.
     * </p>
     *
     * @param revisions copied immutable revisions to make available on the successor platform
     * @return stored revisions in deterministic processing order
     */
    @Transactional
    public List<DppRevisionResponseDTO> importRevisions(List<DppRevisionResponseDTO> revisions) {
        return revisions.stream()
                .sorted(Comparator
                        .comparing(DppRevisionResponseDTO::getDppId, Comparator.nullsFirst(String::compareTo))
                        .thenComparing(DppRevisionResponseDTO::getVersion, Comparator.nullsFirst(Integer::compareTo)))
                .map(this::importRevision)
                .toList();
    }

    private DppRevisionResponseDTO importRevision(DppRevisionResponseDTO revision) {
        DppRevisionSchemaDTO schemaVersion = revision.getSchemaVersion();
        if (schemaVersion == null) {
            throw new IllegalArgumentException("schema_version is required for imported revisions");
        }

        SubjectType subjectType = subjectTypeService.getRequiredSubjectType(schemaVersion.getSubjectType());
        DppSchema schema = schemaService.getRequiredCachedSchema(schemaVersion);
        return revisionService.importExistingRevision(revision, subjectType, schema);
    }
}
