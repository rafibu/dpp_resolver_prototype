package ch.bfh.generic_dpp_platform.schemas.services;

import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionSchemaDTO;
import ch.bfh.generic_dpp_platform.schemas.dtos.DppSchemaDTO;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchema;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchemaId;
import ch.bfh.generic_dpp_platform.schemas.repositories.DppSchemaRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.NoSuchElementException;

/**
 *
 * @author rbu on 21.04.2026
 */
@Service
@RequiredArgsConstructor
public class DppSchemaService {

    private static final ObjectMapper MAPPER = new ObjectMapper().findAndRegisterModules();

    private final DppSchemaRepository dppSchemaRepository;
    private final SubjectTypeRepository subjectTypeRepository;

    /**
     * Retrieves an exact schema defined by the specified subject type name and version numbers.
     *
     * @param subjectTypeName the name of the subject type to which the schema belongs
     * @param major           the major version of the schema
     * @param minor           the minor version of the schema
     * @return a {@link DppSchemaDTO} representing the schema with the specified details,
     * or null if no schema with this exact version has been loaded from the resolver
     */
    @Transactional(readOnly = true)
    public DppSchemaDTO getExactSchema(String subjectTypeName, int major, int minor) {
        SubjectType subjectType = subjectTypeRepository.findByName(subjectTypeName).orElseThrow();

        DppSchemaId dppSchemaId = DppSchemaId.builder()
                .subjectTypeName(subjectType.getName())
                .majorVersion(major)
                .minorVersion(minor)
                .build();

        return dppSchemaRepository.findById(dppSchemaId).map(DppSchemaService::toDTO).orElse(null);
    }

    /**
     * Retrieves the most recent schema associated with the specified subject type name.
     *
     * @param subjectTypeName the name of the subject type to which the schema belongs
     * @return a {@link DppSchemaDTO} representing the most recent schema for the specified subject type,
     * or null if no schema has been loaded from the resolver
     */
    @Transactional(readOnly = true)
    public DppSchemaDTO getCurrentSchema(String subjectTypeName) {
        SubjectType subjectType = subjectTypeRepository.findByName(subjectTypeName).orElseThrow();

        return dppSchemaRepository.findNewestBySubjectType(subjectType).map(DppSchemaService::toDTO).orElse(null);
    }

    /**
     * Load the exact cached schema entity named by a DPP revision.
     * <p>
     * This method is intentionally cache-only. Administrative migration import does not publish schemas and does
     * not silently change platform capabilities; the caller must have registered the subject type and cached the
     * exact schema through the existing schema endpoints before importing copied revisions. This keeps the import
     * endpoint as orchestration over known platform paths rather than a second schema-management path.
     * </p>
     *
     * @param schemaVersion exact schema reference carried by the imported revision
     * @return cached schema entity used for payload validation
     * @throws IllegalArgumentException if the schema reference is incomplete
     * @throws NoSuchElementException   if the exact schema is not cached on this platform
     */
    @Transactional(readOnly = true)
    public DppSchema getRequiredCachedSchema(DppRevisionSchemaDTO schemaVersion) {
        if (schemaVersion == null) {
            throw new IllegalArgumentException("schema_version is required for imported revisions");
        }
        if (schemaVersion.getSubjectType() == null || schemaVersion.getSubjectType().isBlank()
                || schemaVersion.getMajorVersion() == null
                || schemaVersion.getMinorVersion() == null) {
            throw new IllegalArgumentException("schema_version must contain subject_type, major_version, and minor_version");
        }

        DppSchemaId schemaId = DppSchemaId.builder()
                .subjectTypeName(schemaVersion.getSubjectType())
                .majorVersion(schemaVersion.getMajorVersion())
                .minorVersion(schemaVersion.getMinorVersion())
                .build();

        return dppSchemaRepository.findById(schemaId)
                .orElseThrow(() -> new NoSuchElementException("Schema not cached: " + schemaId));
    }

    private static DppSchema fromDTO(DppSchemaDTO dppSchemaDTO, SubjectType subjectType) {
        return DppSchema.builder()
                .subjectType(subjectType)
                .id(DppSchemaId.builder()
                        .majorVersion(dppSchemaDTO.getMajorVersion())
                        .minorVersion(dppSchemaDTO.getMinorVersion())
                        .build())
                .publishedAt(dppSchemaDTO.getPublishedAt())
                .schemaDocument(MAPPER.valueToTree(dppSchemaDTO.getSchemaDocument()))
                .build();
    }

    private static DppSchemaDTO toDTO(DppSchema dppSchema) {
        return DppSchemaDTO.builder()
                .subjectType(dppSchema.getSubjectType().getName())
                .majorVersion(dppSchema.getId().getMajorVersion())
                .minorVersion(dppSchema.getId().getMinorVersion())
                .publishedAt(dppSchema.getPublishedAt())
                .schemaDocument(MAPPER.convertValue(dppSchema.getSchemaDocument(), Object.class))
                .build();
    }
}
