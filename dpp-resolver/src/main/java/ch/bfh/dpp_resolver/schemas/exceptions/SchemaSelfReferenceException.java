package ch.bfh.dpp_resolver.schemas.exceptions;

import lombok.Getter;

/**
 * Thrown when a schema artefact declares a hard-reference field targeting its own subject type,
 * which is a degenerate cycle and violates Invariant I6.
 *
 * @see ch.bfh.dpp_resolver.schemas.services.SchemaCycleDetector
 */
@Getter
public class SchemaSelfReferenceException extends RuntimeException {
    private final String subjectType;

    public SchemaSelfReferenceException(String message, String subjectType) {
        super(message);
        this.subjectType = subjectType;
    }
}
