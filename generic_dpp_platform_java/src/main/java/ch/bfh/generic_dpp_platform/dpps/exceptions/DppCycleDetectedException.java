package ch.bfh.generic_dpp_platform.dpps.exceptions;

import lombok.Getter;

import java.util.List;

/**
 * Exception thrown when a dependency cycle is detected.
 * Mapped to HTTP 409 Conflict.
 */
@Getter
public class DppCycleDetectedException extends RuntimeException {
    private final List<String> cyclePath;

    public DppCycleDetectedException(String message, List<String> cyclePath) {
        super(message);
        this.cyclePath = cyclePath;
    }
}
