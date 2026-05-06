package ch.bfh.generic_dpp_platform.admin.controllers;

import ch.bfh.generic_dpp_platform.common.dtos.ApiError;
import ch.bfh.generic_dpp_platform.dpps.exceptions.DppAlreadyExistsException;
import ch.bfh.generic_dpp_platform.dpps.exceptions.DppCycleDetectedException;
import ch.bfh.generic_dpp_platform.dpps.exceptions.DppReferenceResolutionException;
import ch.bfh.generic_dpp_platform.dpps.exceptions.DppRevisionConflictException;
import ch.bfh.generic_dpp_platform.dpps.exceptions.SchemaValidationException;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.ExceptionHandler;

import java.time.LocalDateTime;
import java.util.List;
import java.util.NoSuchElementException;

@ControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ApiError> handleIllegalArgumentException(IllegalArgumentException ex, HttpServletRequest request) {
        return buildErrorResponse(HttpStatus.BAD_REQUEST, "Invalid Argument", ex.getMessage(), null, request);
    }

    @ExceptionHandler(SchemaValidationException.class)
    public ResponseEntity<ApiError> handleSchemaValidationException(SchemaValidationException ex, HttpServletRequest request) {
        return buildErrorResponse(HttpStatus.BAD_REQUEST, "Schema Validation Failed", ex.getMessage(), ex.getValidationErrors(), request);
    }

    @ExceptionHandler(DppAlreadyExistsException.class)
    public ResponseEntity<ApiError> handleDppAlreadyExistsException(DppAlreadyExistsException ex, HttpServletRequest request) {
        return buildErrorResponse(HttpStatus.CONFLICT, "DPP Already Exists", ex.getMessage(), null, request);
    }

    @ExceptionHandler(DppRevisionConflictException.class)
    public ResponseEntity<ApiError> handleDppRevisionConflictException(DppRevisionConflictException ex, HttpServletRequest request) {
        return buildErrorResponse(HttpStatus.CONFLICT, "Revision Conflict", ex.getMessage(), null, request);
    }

    @ExceptionHandler(DppReferenceResolutionException.class)
    public ResponseEntity<ApiError> handleDppReferenceResolutionException(DppReferenceResolutionException ex, HttpServletRequest request) {
        List<String> details = ex.getUnresolvedReference() != null ? List.of(ex.getUnresolvedReference()) : null;
        return buildErrorResponse(HttpStatus.FAILED_DEPENDENCY, "Failed Dependency", ex.getMessage(), details, request);
    }

    @ExceptionHandler(DppCycleDetectedException.class)
    public ResponseEntity<ApiError> handleDppCycleDetectedException(DppCycleDetectedException ex, HttpServletRequest request) {
        return buildErrorResponse(HttpStatus.CONFLICT, "Cycle Detected", ex.getMessage(), ex.getCyclePath(), request);
    }

    @ExceptionHandler(NoSuchElementException.class)
    public ResponseEntity<ApiError> handleNoSuchElementException(NoSuchElementException ex, HttpServletRequest request) {
        return buildErrorResponse(HttpStatus.NOT_FOUND, "Not Found", ex.getMessage(), null, request);
    }

    private ResponseEntity<ApiError> buildErrorResponse(HttpStatus status, String error, String message, List<String> details, HttpServletRequest request) {
        ApiError apiError = ApiError.builder()
                .error(error)
                .message(message)
                .details(details)
                .timestamp(LocalDateTime.now())
                .path(request.getRequestURI())
                .build();
        return ResponseEntity.status(status).body(apiError);
    }
}
