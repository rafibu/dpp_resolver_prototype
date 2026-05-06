package ch.bfh.generic_dpp_platform.dpps.services;

import ch.bfh.generic_dpp_platform.admin.services.PlatformConfigService;
import ch.bfh.generic_dpp_platform.dpps.dtos.DppRevisionResponseDTO;
import ch.bfh.generic_dpp_platform.dpps.exceptions.DppCycleDetectedException;
import ch.bfh.generic_dpp_platform.dpps.models.DppReference;
import ch.bfh.generic_dpp_platform.dpps.models.DppRevision;
import ch.bfh.generic_dpp_platform.dpps.models.DppRevisionId;
import ch.bfh.generic_dpp_platform.dpps.models.ReferencedDppRevision;
import ch.bfh.generic_dpp_platform.dpps.models.ReferencedDppRevisionId;
import ch.bfh.generic_dpp_platform.dpps.repositories.DppRevisionRepository;
import ch.bfh.generic_dpp_platform.dpps.utils.DppReferenceExtractor;
import ch.bfh.generic_dpp_platform.dpps.utils.DppUtil;
import ch.bfh.generic_dpp_platform.schemas.connectors.ResolverConnector;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.*;
import java.util.stream.Collectors;

/**
 * Service for bounded hard-dependency cycle detection.
 * Traverses at most 3 dependency rounds to detect cycles.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class DppCycleDetectionService {

    private final DppRevisionRepository dppRevisionRepository;
    private final DppRevisionCacheService cacheService;
    private final ResolverConnector resolverConnector;
    private final DppReferenceExtractor referenceExtractor;
    private final PlatformConfigService platformConfigService;
    private final ObjectMapper objectMapper = new ObjectMapper();

    private static final int MAX_ROUNDS = 3;

    /**
     * Detects cycles starting from a candidate revision.
     * The prototype intentionally limits transitive cycle traversal to 3 rounds
     * to avoid traversing the entire federated DPP network.
     * Cycles deeper than 3 dependency rounds are not guaranteed to be detected.
     *
     * @param subjectType   The subject type of the candidate.
     * @param dppId         The DPP ID of the candidate.
     * @param version       The version of the candidate.
     * @param initialPayload The payload of the candidate revision.
     * @throws DppCycleDetectedException if a cycle is detected within 3 rounds.
     */
    public void detectCycles(String subjectType, String dppId, int version, Map<String, Object> initialPayload) {
        log.info("Starting bounded cycle detection for {}/{} version {} (max rounds: {})", subjectType, dppId, version, MAX_ROUNDS);

        String candidateKey = formatKey(subjectType, dppId, version);

        // Use a queue for BFS and keep track of paths to report cycle if found
        Queue<List<String>> queue = new LinkedList<>();

        // Initial round: references in the candidate revision
        List<DppReference> initialRefs = referenceExtractor.extractReferences(objectMapper.valueToTree(initialPayload));
        for (DppReference ref : initialRefs) {
            if (ref.type() == DppReference.DependencyType.HARD) {
                String nextKey = formatKey(ref.subjectType(), ref.dppId(), ref.version());
                List<String> path = new ArrayList<>();
                path.add(candidateKey);
                path.add(nextKey);

                // Immediate check for direct cycle
                if (nextKey.equals(candidateKey)) {
                    log.error("Direct cycle detected: {}", String.join(" -> ", path));
                    throw new DppCycleDetectedException("Hard-dependency cycle detected", path);
                }

                queue.add(path);
            }
        }

        Set<String> visited = new HashSet<>();
        // Note: Do NOT add candidateKey to visited yet if we want to detect re-entry
        // BUT we actually check nextKey == candidateKey before adding to queue now.
        // So visited can contain candidateKey to avoid redundant work if someone else points to it,
        // but we must check re-entry specifically.
        visited.add(candidateKey);

        int currentRound = 1;
        int elementsInCurrentRound = queue.size();
        int elementsInNextRound = 0;

        while (!queue.isEmpty() && currentRound <= MAX_ROUNDS) {
            List<String> path = queue.poll();
            elementsInCurrentRound--;

            String currentKey = path.get(path.size() - 1);

            if (!visited.contains(currentKey)) {
                visited.add(currentKey);

                // Fetch references for currentKey
                List<DppReference> refs = fetchReferences(currentKey);
                for (DppReference ref : refs) {
                    if (ref.type() == DppReference.DependencyType.HARD) {
                        String nextKey = formatKey(ref.subjectType(), ref.dppId(), ref.version());
                        List<String> nextPath = new ArrayList<>(path);
                        nextPath.add(nextKey);

                        // Check candidate re-entry before visited-pruning
                        if (nextKey.equals(candidateKey)) {
                            log.error("Transitive cycle detected: {}", String.join(" -> ", nextPath));
                            throw new DppCycleDetectedException("Hard-dependency cycle detected", nextPath);
                        }

                        // Visited pruning for other nodes
                        if (!visited.contains(nextKey)) {
                            queue.add(nextPath);
                            elementsInNextRound++;
                        }
                    }
                }
            }

            if (elementsInCurrentRound == 0) {
                if (elementsInNextRound > 0 && currentRound < MAX_ROUNDS) {
                    currentRound++;
                    elementsInCurrentRound = elementsInNextRound;
                    elementsInNextRound = 0;
                    log.debug("Moving to cycle detection round {}", currentRound);
                } else {
                    // Either no more elements or we reached the limit
                    if (elementsInNextRound > 0) {
                        log.info("Cycle detection reached max traversal depth of {}. Bounding traversal. Elements in next round skipped: {}", MAX_ROUNDS, elementsInNextRound);
                    }
                    break;
                }
            }
        }

        log.info("Cycle detection completed. No cycles found within {} rounds.", MAX_ROUNDS);
    }

    private List<DppReference> fetchReferences(String key) {
        // key format: subjectType/dppId/version
        String[] parts = key.split("/");
        if (parts.length != 3) return Collections.emptyList();

        String subjectType = parts[0];
        String dppId = parts[1];
        int version = Integer.parseInt(parts[2]);

        Map<String, Object> payload = null;

        // 1. Check if local
        if (dppId.startsWith(platformConfigService.getPlatformConfig().getIssuerId())) {
            Optional<DppRevision> local = dppRevisionRepository.findById(new DppRevisionId(version, dppId));
            if (local.isPresent()) {
                payload = local.get().getDppDocument();
            }
        }

        // 2. Check cache if not local or not found locally
        if (payload == null) {
            Optional<ReferencedDppRevision> cached = cacheService.getCachedRevision(dppId, version);
            if (cached.isPresent()) {
                payload = cached.get().getDppDocument();
            }
        }

        // 3. Resolve via Resolver if still not found
        if (payload == null) {
            try {
                DppRevisionResponseDTO resolved = resolverConnector.resolveDppRevision(subjectType, dppId, version);
                if (resolved == null) {
                    log.warn("Resolver returned null for {} during cycle detection", key);
                    return Collections.emptyList();
                }
                // Cache it for future use (including later rounds or other issuances)
                ReferencedDppRevision external = ReferencedDppRevision.builder()
                        .id(new ReferencedDppRevisionId(dppId, version))
                        .subjectType(subjectType)
                        .schemaSubjectType(resolved.getSchemaVersion().getSubjectType())
                        .schemaMajorVersion(resolved.getSchemaVersion().getMajorVersion())
                        .schemaMinorVersion(resolved.getSchemaVersion().getMinorVersion())
                        .dppDocument((Map<String, Object>) resolved.getDppPayload())
                        .hashedDocument(DppUtil.hexToHash(resolved.getPayloadHash()))
                        .fetchedAt(Instant.now())
                        .build();
                cacheService.cacheRevision(external);
                payload = external.getDppDocument();
            } catch (Exception e) {
                log.warn("Failed to resolve reference {} during cycle detection: {}", key, e.getMessage());
                // If we can't resolve it, we can't check its dependencies, but it's not necessarily a cycle.
                // However, the issuance flow should have already resolved all direct hard references.
                // For transitive ones, if we can't resolve them, we just stop traversing that branch.
                return Collections.emptyList();
            }
        }

        if (payload != null) {
            return referenceExtractor.extractReferences(objectMapper.valueToTree(payload));
        }

        return Collections.emptyList();
    }

    private String formatKey(String subjectType, String dppId, int version) {
        return subjectType + "/" + dppId + "/" + version;
    }
}
