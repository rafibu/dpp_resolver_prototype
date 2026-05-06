package ch.bfh.generic_dpp_platform.dpps.exceptions;

import lombok.Getter;

import java.util.List;

/**
 * Exception thrown when a DPP reference cannot be resolved.
 * Mapped to HTTP 424 Failed Dependency.
 */
@Getter
public class DppReferenceResolutionException extends RuntimeException {
    private final String unresolvedReference;

    public DppReferenceResolutionException(String message) {
        this(message, null);
    }

    public DppReferenceResolutionException(String message, String unresolvedReference) {
        super(message);
        this.unresolvedReference = unresolvedReference;
    }
}
