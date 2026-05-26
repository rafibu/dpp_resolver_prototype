package ch.bfh.generic_dpp_platform.admin.dtos;

import com.fasterxml.jackson.annotation.JsonFormat;
import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;

/**
 * Structured API error response, used in the {@link ch.bfh.generic_dpp_platform.admin.controllers.GlobalExceptionHandler GlobalExceptionHandler}
 */
@Data
@Builder
public class ApiError {
    private String error;
    private String message;
    private List<String> details;

    @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "yyyy-MM-dd'T'HH:mm:ss.SSS")
    private LocalDateTime timestamp;

    private String path;
}
