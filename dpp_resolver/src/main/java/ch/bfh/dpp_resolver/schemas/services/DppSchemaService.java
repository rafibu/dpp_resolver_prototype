package ch.bfh.dpp_resolver.schemas.services;

import ch.bfh.dpp_resolver.schemas.dtos.DppSchemaDTO;
import ch.bfh.dpp_resolver.schemas.exceptions.SchemaCycleException;
import ch.bfh.dpp_resolver.schemas.exceptions.SchemaSelfReferenceException;
import ch.bfh.dpp_resolver.schemas.models.DppSchema;
import ch.bfh.dpp_resolver.schemas.models.DppSchemaId;
import ch.bfh.dpp_resolver.admin.models.SubjectType;
import ch.bfh.dpp_resolver.schemas.models.SchemaDependency;
import ch.bfh.dpp_resolver.schemas.repositories.DppSchemaRepository;
import ch.bfh.dpp_resolver.admin.repositories.SubjectTypeRepository;
import ch.bfh.dpp_resolver.schemas.repositories.SchemaDependencyRepository;
import ch.bfh.dpp_resolver.utils.JsonUtil;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.persistence.EntityNotFoundException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.jspecify.annotations.NonNull;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.stream.Collectors;

/**
 *
 * @author rbu on 20.04.2026
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class DppSchemaService {

    private final DppSchemaRepository dppSchemaRepository;
    private final SubjectTypeRepository subjectTypeRepository;
    private final HardReferenceExtractor hardReferenceExtractor;
    private final SchemaCycleDetector schemaCycleDetector;
    private final SchemaDependencyRepository schemaDependencyRepository;
    private final ObjectMapper objectMapper = new ObjectMapper().findAndRegisterModules();


    @Transactional(readOnly = true)
    public List<DppSchemaDTO> findAllBySubjectType(String subjectTypeName) {
        SubjectType subjectType = subjectTypeRepository.findByName(subjectTypeName).orElseThrow();

        return dppSchemaRepository.findAllBySubjectType(subjectType)
                .stream()
                .map(this::mapToDTO).toList();
    }

    @Transactional(readOnly = true)
    public DppSchemaDTO findActiveBySubjectType(String subjectTypeName) {
        SubjectType subjectType = subjectTypeRepository.findByName(subjectTypeName).orElseThrow();
        DppSchema activeSchema = dppSchemaRepository.findActiveBySubjectType(subjectType);
        if (activeSchema == null) {
            throw new NoSuchElementException("No active schema found for SubjectType: " + subjectTypeName);
        }
        return mapToDTO(activeSchema);
    }

    @Transactional(readOnly = true)
    public DppSchemaDTO findExactSchema(String subjectTypeName, int majorVersion, int minorVersion) {
        SubjectType subjectType = subjectTypeRepository.findByName(subjectTypeName).orElseThrow();
        DppSchema dppSchema = dppSchemaRepository.findExactSchema(subjectType, majorVersion, minorVersion).orElseThrow();
        return mapToDTO(dppSchema);
    }

    @Transactional
    public DppSchemaDTO save(DppSchemaDTO dto) {
        SubjectType subjectType = subjectTypeRepository.findByName(dto.getSubjectType()).orElseThrow();
        DppSchema dppSchema = fromDto(dto, subjectType);

        if (dppSchemaRepository.existsById(dppSchema.getId())) {
            throw new IllegalArgumentException("Published schema artifacts are immutable");
        }

        assertValidSchema(dppSchema);

        // Task R-8: Cycle Detection
        List<String> targetNames = hardReferenceExtractor.extractHardReferenceTargets(dppSchema.getSchemaDocument());
        List<SchemaCycleDetector.DependencyEdge> existingEdges = schemaDependencyRepository.findAllWithSubjectTypes()
                .stream()
                .map(sd -> new SchemaCycleDetector.DependencyEdge(
                        sd.getFromSubjectType().getName(),
                        sd.getToSubjectType().getName()
                ))
                .toList();

        SchemaCycleDetector.CycleCheckResult cycleResult = schemaCycleDetector.checkForCycle(
                subjectType.getName(),
                targetNames,
                existingEdges
        );

        if (cycleResult instanceof SchemaCycleDetector.CycleCheckResult.SelfReference selfRef) {
            log.warn("Rejected schema publication for '{}' due to self-reference", subjectType.getName());
            throw new SchemaSelfReferenceException(
                    String.format("Schema '%s' %d.%d declares a hard reference to its own subject type",
                            subjectType.getName(), dppSchema.getId().getMajorVersion(), dppSchema.getId().getMinorVersion()),
                    subjectType.getName()
            );
        } else if (cycleResult instanceof SchemaCycleDetector.CycleCheckResult.CycleDetected cycleDetected) {
            String pathStr = String.join(" -> ", cycleDetected.path());
            log.warn("Rejected schema publication for '{}' due to cycle: {}", subjectType.getName(), pathStr);
            throw new SchemaCycleException(
                    String.format("Publishing schema '%s' %d.%d would introduce a cycle: %s",
                            subjectType.getName(), dppSchema.getId().getMajorVersion(), dppSchema.getId().getMinorVersion(), pathStr),
                    cycleDetected.path()
            );
        }

        DppSchema savedSchema = dppSchemaRepository.save(dppSchema);

        // Persist dependency edges
        for (String targetName : targetNames) {
            SubjectType targetSubjectType = subjectTypeRepository.findByName(targetName)
                    .orElseThrow(() -> new IllegalArgumentException("Unknown target subject type: " + targetName));

            SchemaDependency.SchemaDependencyId depId = new SchemaDependency.SchemaDependencyId(
                    subjectType.getId(),
                    targetSubjectType.getId(),
                    savedSchema.getId().getMajorVersion(),
                    savedSchema.getId().getMinorVersion()
            );
            SchemaDependency dependency = new SchemaDependency(depId, subjectType, targetSubjectType, savedSchema);
            schemaDependencyRepository.save(dependency);
        }

        log.info("Published schema '{}' {}.{}", subjectType.getName(), savedSchema.getId().getMajorVersion(), savedSchema.getId().getMinorVersion());
        return mapToDTO(savedSchema);
    }

    private void assertValidSchema(DppSchema dppSchema) {
        if (dppSchema.getSubjectType() == null) {
            throw new IllegalArgumentException("SubjectType must not be null");
        }
        if (dppSchema.getId().invalid()) {
            throw new IllegalArgumentException("SchemaId must be valid [" + dppSchema.getId() + "]");
        }

        DppSchema currentActiveSchema = dppSchemaRepository.findActiveBySubjectType(dppSchema.getSubjectType());
        if (currentActiveSchema == null) {
            if (dppSchema.getSchemaDocument() == null || dppSchema.getSchemaDocument().isEmpty()) {
                throw new IllegalArgumentException("SchemaDocument must not be empty");
            }
            return;
        }

        DppSchemaId currentActiveSchemaId = currentActiveSchema.getId();
        DppSchemaId newSchemaId = dppSchema.getId();
        if (Objects.equals(currentActiveSchemaId.getMajorVersion(), newSchemaId.getMajorVersion())) {
            if (currentActiveSchemaId.getMinorVersion() + 1 != newSchemaId.getMinorVersion()) {
                throw new IllegalArgumentException("Major or Minor version must be incremented by 1");
            }
            //minor version update means the JSON Schema must be backwards compatible
            JsonUtil.assertIsBackwardsCompatible(currentActiveSchema.getSchemaDocument(), dppSchema.getSchemaDocument());
            return;
        }
        if (currentActiveSchemaId.getMajorVersion() + 1 != newSchemaId.getMajorVersion()) {
            throw new IllegalArgumentException("Major version must be incremented by 1");
        }
    }

    private DppSchema fromDto(DppSchemaDTO dto, SubjectType subjectType) {
        DppSchema dppSchema = new DppSchema();
        DppSchemaId id = new DppSchemaId(dto.getMajorVersion(), dto.getMinorVersion(), subjectType.getId());
        dppSchema.setId(id);
        dppSchema.setSubjectType(subjectType);
        dppSchema.setPublishedAt(Instant.now());
        dppSchema.setSchemaDocument(objectMapper.valueToTree(dto.getSchemaDocument()));
        return dppSchema;
    }

    private DppSchemaDTO mapToDTO(DppSchema dppSchema) {
        return DppSchemaDTO.builder()
                .subjectType(dppSchema.getSubjectType().getName())
                .majorVersion(dppSchema.getId().getMajorVersion())
                .minorVersion(dppSchema.getId().getMinorVersion())
                .schemaDocument(objectMapper.convertValue(dppSchema.getSchemaDocument(), Object.class))
                .publishedAt(dppSchema.getPublishedAt())
                .build();
    }

}
