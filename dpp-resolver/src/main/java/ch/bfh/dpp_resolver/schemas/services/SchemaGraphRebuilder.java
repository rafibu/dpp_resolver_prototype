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

import java.util.*;
import java.util.stream.Collectors;

/**
 * Self-healing startup component for the schema dependency graph (Definition 13).
 *
 * <p>Runs once via {@link PostConstruct}. Compares the persisted {@code schema_dependency}
 * table against the edges that would be derived from the stored {@link DppSchema} artefacts.
 * If drift is detected, the table is rebuilt from scratch. After a rebuild, the graph is
 * verified against Invariant I6 and any cycle is logged as an error.</p>
 *
 * <p>Drift should not occur during normal operation because {@link DppSchemaService} keeps the
 * table in sync on every {@code publishSchema} call. The rebuild is a last-resort guard for
 * partial failures or direct database edits.</p>
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class SchemaGraphRebuilder {

    private final DppSchemaRepository dppSchemaRepository;
    private final SchemaDependencyRepository schemaDependencyRepository;
    private final SubjectTypeRepository subjectTypeRepository;
    private final HardReferenceExtractor hardReferenceExtractor;
    private final SchemaCycleDetector schemaCycleDetector;

    /**
     * Checks whether the {@code schema_dependency} table is consistent with the stored schemas
     * and rebuilds it if not. After a successful rebuild, verifies Invariant I6 via
     * {@link #checkAndLogCycles()}.
     *
     * <p>The expected edge set is derived by re-running {@link HardReferenceExtractor} over every
     * stored {@link DppSchema}. If expected and actual edge-id sets differ, the table is cleared
     * and repopulated.</p>
     */
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
                subjectTypeRepository.findByName(targetName).ifPresent(targetType -> expectedIds.add(new SchemaDependency.SchemaDependencyId(
                        schema.getSubjectType().getId(),
                        targetType.getId(),
                        schema.getId().getMajorVersion(),
                        schema.getId().getMinorVersion()
                )));
            }
        }

        if (!expectedIds.equals(existingIds)) {
            log.warn("Schema dependency graph mismatch detected (Expected: {}, Existing: {}). Rebuilding...", expectedIds.size(), existingIds.size());
            rebuild(allSchemas);
            checkAndLogCycles();
        } else {
            log.info("Schema dependency graph is consistent ({} edges).", existingIds.size());
        }
    }

    /**
     * Clears the {@code schema_dependency} table and repopulates it from the given schemas.
     *
     * <p>For each schema, {@link HardReferenceExtractor} is invoked to obtain the set of
     * hard-reference target subject types. One {@link SchemaDependency} edge is persisted per
     * (source subject type, target subject type, schema version) triple. Target subject types
     * not present in the {@code subject_type} table are logged as errors and skipped.</p>
     *
     * @param allSchemas the full list of stored schema artefacts to derive edges from
     */
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

    /**
     * Verifies Invariant I6 on the rebuilt {@code schema_dependency} table and logs an error
     * for every detected cycle or self-reference.
     *
     * <p>A cycle here indicates corrupt dependency data, because {@link DppSchemaService}
     * rejects schema artefacts that would introduce one. If a cycle is found, the resolver is in
     * an inconsistent state and manual intervention is required.</p>
     *
     * <p>For each distinct source subject type, {@link SchemaCycleDetector#checkForCycle} is
     * called with that type's outgoing edges as the candidate and all remaining edges as existing.
     * Duplicate cycle reports for the same path are suppressed.</p>
     */
    private void checkAndLogCycles() {
        List<SchemaDependency> allDeps = schemaDependencyRepository.findAll();

        List<SchemaCycleDetector.DependencyEdge> allEdges = allDeps.stream()
                .map(d -> new SchemaCycleDetector.DependencyEdge(
                        d.getFromSubjectType().getName(),
                        d.getToSubjectType().getName()))
                .toList();

        Map<String, List<String>> bySource = new HashMap<>();
        for (SchemaDependency dep : allDeps) {
            bySource.computeIfAbsent(dep.getFromSubjectType().getName(), _ -> new ArrayList<>())
                    .add(dep.getToSubjectType().getName());
        }

        Set<String> reported = new HashSet<>();
        for (Map.Entry<String, List<String>> entry : bySource.entrySet()) {
            String sourceType = entry.getKey();
            List<String> targets = entry.getValue();

            List<SchemaCycleDetector.DependencyEdge> otherEdges = allEdges.stream()
                    .filter(e -> !e.getFrom().equals(sourceType))
                    .collect(Collectors.toList());

            SchemaCycleDetector.CycleCheckResult result = schemaCycleDetector.checkForCycle(sourceType, targets, otherEdges);

            if (result instanceof SchemaCycleDetector.CycleCheckResult.CycleDetected(List<String> path)) {
                String cycleStr = String.join(" -> ", path);
                if (reported.add(cycleStr)) {
                    log.error("I6 violation in rebuilt schema dependency graph: cycle [{}]. " +
                            "The resolver is in an inconsistent state. Manual intervention is required.", cycleStr);
                }
            } else if (result instanceof SchemaCycleDetector.CycleCheckResult.SelfReference(String subjectType)) {
                if (reported.add("self:" + subjectType)) {
                    log.error("I6 violation in rebuilt schema dependency graph: subject type '{}' " +
                            "has a self-reference. Manual intervention is required.", subjectType);
                }
            }
        }
    }
}