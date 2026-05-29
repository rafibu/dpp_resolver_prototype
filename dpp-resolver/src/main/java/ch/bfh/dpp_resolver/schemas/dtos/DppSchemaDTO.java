package ch.bfh.dpp_resolver.schemas.dtos;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import com.fasterxml.jackson.databind.JsonNode;

import java.time.Instant;

/**
 *
 * @author rbu on 20.04.2026
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class DppSchemaDTO {
    String subjectType;
    Integer majorVersion;
    Integer minorVersion;
    Object schemaDocument;
    Instant publishedAt;
}
