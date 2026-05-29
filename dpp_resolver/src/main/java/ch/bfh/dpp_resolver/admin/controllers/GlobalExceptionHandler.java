package ch.bfh.dpp_resolver.admin.controllers;

import ch.bfh.dpp_resolver.schemas.exceptions.SchemaCycleException;
import ch.bfh.dpp_resolver.schemas.exceptions.SchemaSelfReferenceException;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.Map;

@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(SchemaCycleException.class)
    public ResponseEntity<?> handleSchemaCycle(SchemaCycleException ex) {
        return ResponseEntity.unprocessableContent().body(Map.of(
            "error", "schema_cycle_detected",
            "message", ex.getMessage(),
            "cycle_path", ex.getCyclePath()
        ));
    }

    @ExceptionHandler(SchemaSelfReferenceException.class)
    public ResponseEntity<?> handleSchemaSelfReference(SchemaSelfReferenceException ex) {
        return ResponseEntity.unprocessableContent().body(Map.of(
            "error", "schema_self_reference",
            "message", ex.getMessage(),
            "subject_type", ex.getSubjectType()
        ));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<?> handleIllegalArgument(IllegalArgumentException ex) {
        return ResponseEntity.badRequest().body(Map.of(
            "error", "invalid_argument",
            "message", ex.getMessage()
        ));
    }
}
