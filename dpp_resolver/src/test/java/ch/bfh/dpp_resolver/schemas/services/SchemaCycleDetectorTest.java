package ch.bfh.dpp_resolver.schemas.services;

import ch.bfh.dpp_resolver.schemas.services.SchemaCycleDetector.CycleCheckResult;
import ch.bfh.dpp_resolver.schemas.services.SchemaCycleDetector.DependencyEdge;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class SchemaCycleDetectorTest {

    private final SchemaCycleDetector detector = new SchemaCycleDetector();

    @Test
    void testAcyclic() {
        List<DependencyEdge> existing = List.of(
            new DependencyEdge("A", "B"),
            new DependencyEdge("B", "C")
        );
        CycleCheckResult result = detector.checkForCycle("D", List.of("A"), existing);
        assertTrue(result instanceof CycleCheckResult.Acyclic);
    }

    @Test
    void testDirectCycle() {
        List<DependencyEdge> existing = List.of(
            new DependencyEdge("A", "B")
        );
        CycleCheckResult result = detector.checkForCycle("B", List.of("A"), existing);
        assertTrue(result instanceof CycleCheckResult.CycleDetected);
        List<String> path = ((CycleCheckResult.CycleDetected) result).path();
        assertEquals(List.of("B", "A", "B"), path);
    }

    @Test
    void testTransitiveCycle() {
        List<DependencyEdge> existing = List.of(
            new DependencyEdge("A", "B"),
            new DependencyEdge("B", "C")
        );
        CycleCheckResult result = detector.checkForCycle("C", List.of("A"), existing);
        assertTrue(result instanceof CycleCheckResult.CycleDetected);
        List<String> path = ((CycleCheckResult.CycleDetected) result).path();
        assertEquals(List.of("C", "A", "B", "C"), path);
    }

    @Test
    void testSelfReference() {
        CycleCheckResult result = detector.checkForCycle("A", List.of("A"), new ArrayList<>());
        assertTrue(result instanceof CycleCheckResult.SelfReference);
    }

    @Test
    void testDiamondAcyclic() {
        List<DependencyEdge> existing = List.of(
            new DependencyEdge("A", "B"),
            new DependencyEdge("A", "C"),
            new DependencyEdge("B", "D"),
            new DependencyEdge("C", "D")
        );
        CycleCheckResult result = detector.checkForCycle("X", List.of("A"), existing);
        assertTrue(result instanceof CycleCheckResult.Acyclic);
    }

    @Test
    void testDiamondCycle() {
        List<DependencyEdge> existing = List.of(
            new DependencyEdge("A", "B"),
            new DependencyEdge("A", "C"),
            new DependencyEdge("B", "D"),
            new DependencyEdge("C", "D")
        );
        CycleCheckResult result = detector.checkForCycle("D", List.of("A"), existing);
        assertTrue(result instanceof CycleCheckResult.CycleDetected);
        List<String> path = ((CycleCheckResult.CycleDetected) result).path();
        // Path could be D -> A -> B -> D or D -> A -> C -> D
        assertTrue(path.equals(List.of("D", "A", "B", "D")) || path.equals(List.of("D", "A", "C", "D")));
    }
}
