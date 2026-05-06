package ch.bfh.dpp_resolver.schemas.exceptions;

import lombok.Getter;

@Getter
public class SchemaSelfReferenceException extends RuntimeException {
    private final String subjectType;

    public SchemaSelfReferenceException(String message, String subjectType) {
        super(message);
        this.subjectType = subjectType;
    }
}
