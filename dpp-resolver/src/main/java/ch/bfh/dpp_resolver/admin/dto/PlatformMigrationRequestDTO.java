package ch.bfh.dpp_resolver.admin.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * DTO used to migrate an existing issuer to a known target platform.
 *
 * @author rbu on 01.06.2026
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class PlatformMigrationRequestDTO {
    private String platform;
    private String newResolutionUrl;
}
