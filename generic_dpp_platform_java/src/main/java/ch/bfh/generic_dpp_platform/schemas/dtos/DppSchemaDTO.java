package ch.bfh.generic_dpp_platform.schemas.dtos;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

/**
 * <p>
 * Schema as it is fetched from the resolver.
 * </p>
 *
 * @author rbu on 21.04.2026
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
