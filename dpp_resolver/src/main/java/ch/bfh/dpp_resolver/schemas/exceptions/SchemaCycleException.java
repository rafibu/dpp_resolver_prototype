package ch.bfh.dpp_resolver.schemas.exceptions;

import lombok.Getter;

import java.util.List;

@Getter
public class SchemaCycleException extends RuntimeException {
    private final List<String> cyclePath;

    public SchemaCycleException(String message, List<String> cyclePath) {
        super(message);
        this.cyclePath = cyclePath;
    }
}
