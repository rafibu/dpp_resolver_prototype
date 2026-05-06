package ch.bfh.dpp_resolver.schemas.services;

import ch.bfh.dpp_resolver.admin.models.SubjectType;
import ch.bfh.dpp_resolver.admin.repositories.SubjectTypeRepository;
import ch.bfh.dpp_resolver.schemas.models.DppSchema;
import ch.bfh.dpp_resolver.schemas.models.SchemaDependency;
import ch.bfh.dpp_resolver.schemas.repositories.DppSchemaRepository;
import ch.bfh.dpp_resolver.schemas.repositories.SchemaDependencyRepository;
import jakarta.annotation.PostConstruct;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * Rebuilds the schema dependency graph on startup if drift is detected.
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class SchemaGraphRebuilder {

    private final DppSchemaRepository dppSchemaRepository;
    private final SchemaDependencyRepository schemaDependencyRepository;
    private final SubjectTypeRepository subjectTypeRepository;
    private final HardReferenceExtractor hardReferenceExtractor;

    @PostConstruct
    @Transactional
    public void rebuildIfNecessary() {
        List<DppSchema> allSchemas = dppSchemaRepository.findAll();
        Set<SchemaDependency.SchemaDependencyId> existingIds = schemaDependencyRepository.findAll()
                .stream()
                .map(SchemaDependency::getId)
                .collect(Collectors.toSet());

        Set<SchemaDependency.SchemaDependencyId> expectedIds = new HashSet<>();
        for (DppSchema schema : allSchemas) {
            List<String> targets = hardReferenceExtractor.extractHardReferenceTargets(schema.getSchemaDocument());
            for (String targetName : targets) {
                subjectTypeRepository.findByName(targetName).ifPresent(targetType -> {
                    expectedIds.add(new SchemaDependency.SchemaDependencyId(
                            schema.getSubjectType().getId(),
                            targetType.getId(),
                            schema.getId().getMajorVersion(),
                            schema.getId().getMinorVersion()
                    ));
                });
            }
        }

        if (!expectedIds.equals(existingIds)) {
            log.warn("Schema dependency graph mismatch detected (Expected: {}, Existing: {}). Rebuilding...", expectedIds.size(), existingIds.size());
            rebuild(allSchemas);
        } else {
            log.info("Schema dependency graph is consistent ({} edges).", existingIds.size());
        }
    }

    private void rebuild(List<DppSchema> allSchemas) {
        schemaDependencyRepository.deleteAllInBatch();
        for (DppSchema schema : allSchemas) {
            List<String> targets = hardReferenceExtractor.extractHardReferenceTargets(schema.getSchemaDocument());
            for (String targetName : targets) {
                SubjectType targetSubjectType = subjectTypeRepository.findByName(targetName).orElse(null);
                if (targetSubjectType != null) {
                     SchemaDependency.SchemaDependencyId depId = new SchemaDependency.SchemaDependencyId(
                            schema.getSubjectType().getId(),
                            targetSubjectType.getId(),
                            schema.getId().getMajorVersion(),
                            schema.getId().getMinorVersion()
                    );
                    schemaDependencyRepository.save(new SchemaDependency(depId, schema.getSubjectType(), targetSubjectType, schema));
                } else {
                    log.error("Rebuild: Unknown target subject type '{}' in schema '{}' {}.{}",
                            targetName, schema.getSubjectType().getName(), schema.getId().getMajorVersion(), schema.getId().getMinorVersion());
                }
            }
        }
        log.info("Schema dependency graph rebuilt successfully.");
    }
}
