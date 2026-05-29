package ch.bfh.dpp_resolver.schemas.exceptions;

import lombok.Getter;

import java.util.List;

/**
 * Thrown when the {@code publishSchema} operation would introduce a directed cycle into the
 * schema dependency graph (Definition 13), violating Invariant I6.
 *
 * <p>{@link #cyclePath} contains the offending subject-type sequence with the first and last
 * element equal. Example: {@code ["battery", "pv_module", "battery"]}.</p>
 *
 * @see ch.bfh.dpp_resolver.schemas.services.SchemaCycleDetector
 */
@Getter
public class SchemaCycleException extends RuntimeException {
    private final List<String> cyclePath;

    public SchemaCycleException(String message, List<String> cyclePath) {
        super(message);
        this.cyclePath = cyclePath;
    }
}
