package ch.bfh.generic_dpp_platform.dpps.exceptions;

import lombok.Getter;

import java.util.List;

/**
 * Exception thrown when a DPP document fails schema validation.
 */
@Getter
public class SchemaValidationException extends IllegalArgumentException {
    private final List<String> validationErrors;

    public SchemaValidationException(String message, List<String> validationErrors) {
        super(message);
        this.validationErrors = validationErrors;
    }
}
