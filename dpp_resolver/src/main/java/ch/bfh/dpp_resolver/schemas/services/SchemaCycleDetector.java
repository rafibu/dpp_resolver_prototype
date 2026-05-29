package ch.bfh.dpp_resolver.schemas.services;

import lombok.Value;
import org.springframework.stereotype.Service;

import java.util.*;

/**
 * Checks the acyclicity precondition for the {@code publishSchema} operation
 * (precondition P4), enforcing Invariant I6.
 *
 * <p>The schema dependency graph (Definition 13) has subject types as vertices and a directed
 * edge from subject type A to subject type B when any version of a schema for A declares a
 * hard-reference field targeting B. Invariant I6 requires this graph to remain acyclic.</p>
 *
 * <p>By Proposition 1, maintaining I6 at the schema level is sufficient to guarantee that
 * no instance-level cycle can arise in any valid federated state, regardless of which
 * specific revisions DPP platforms reference. The check is therefore performed once at
 * schema publication time, not at DPP issuance time.</p>
 */
@Service
public class SchemaCycleDetector {

    @Value
    public static class DependencyEdge {
        String from;
        String to;
    }

    public sealed interface CycleCheckResult {
        record Acyclic() implements CycleCheckResult {}
        record CycleDetected(List<String> path) implements CycleCheckResult {}
        record SelfReference(String subjectType) implements CycleCheckResult {}
    }

    public CycleCheckResult checkForCycle(
            String candidateSubjectType,
            List<String> candidateTargets,
            List<DependencyEdge> existingEdges
    ) {
        // 1. Check for self-reference
        for (String target : candidateTargets) {
            if (target.equals(candidateSubjectType)) {
                return new CycleCheckResult.SelfReference(candidateSubjectType);
            }
        }

        // 2. Build adjacency map
        // An edge A -> B exists if any version of schema A declares a hard-reference to B
        Map<String, Set<String>> adjacencyMap = new HashMap<>();
        for (DependencyEdge edge : existingEdges) {
            adjacencyMap.computeIfAbsent(edge.getFrom(), _ -> new HashSet<>()).add(edge.getTo());
        }
        
        // Add candidate edges
        for (String target : candidateTargets) {
            adjacencyMap.computeIfAbsent(candidateSubjectType, _ -> new HashSet<>()).add(target);
        }

        // 3. For each candidate target, run iterative DFS to see if we can reach candidateSubjectType
        for (String startNode : candidateTargets) {
            List<String> cyclePath = findPath(startNode, candidateSubjectType, adjacencyMap);
            if (cyclePath != null) {
                // The cycle is: candidateSubjectType -> startNode -> ... -> candidateSubjectType
                List<String> fullPath = new ArrayList<>();
                fullPath.add(candidateSubjectType);
                fullPath.addAll(cyclePath);
                return new CycleCheckResult.CycleDetected(fullPath);
            }
        }

        return new CycleCheckResult.Acyclic();
    }

    private List<String> findPath(String start, String target, Map<String, Set<String>> adjacencyMap) {
        if (start.equals(target)) {
            return Collections.singletonList(target);
        }

        Deque<String> stack = new ArrayDeque<>();
        stack.push(start);

        Map<String, String> parentMap = new HashMap<>();
        parentMap.put(start, null);

        Set<String> visited = new HashSet<>();
        visited.add(start);

        while (!stack.isEmpty()) {
            String current = stack.pop();

            Set<String> neighbors = adjacencyMap.getOrDefault(current, Collections.emptySet());
            for (String neighbor : neighbors) {
                if (neighbor.equals(target)) {
                    // Path found! Reconstruct it.
                    parentMap.put(neighbor, current);
                    return reconstructPath(neighbor, parentMap);
                }
                if (!visited.contains(neighbor)) {
                    visited.add(neighbor);
                    parentMap.put(neighbor, current);
                    stack.push(neighbor);
                }
            }
        }

        return null;
    }

    private List<String> reconstructPath(String target, Map<String, String> parentMap) {
        LinkedList<String> path = new LinkedList<>();
        String curr = target;
        while (curr != null) {
            path.addFirst(curr);
            curr = parentMap.get(curr);
        }
        return path;
    }
}
