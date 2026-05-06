package ch.bfh.generic_dpp_platform.admin.config;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;
import org.hibernate.validator.constraints.URL;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/**
 * Configuration properties for the DPP Platform.
 * Values are typically provided via environment variables:
 * PLATFORM_NAME, BASE_URL, ISSUER_ID, RESOLVER_BASE_URL.
 */
@Data
@Validated
@ConfigurationProperties(prefix = "platform")
public class PlatformProperties {

    @NotBlank(message = "PLATFORM_NAME must not be blank")
    private String platformName;

    @NotBlank(message = "BASE_URL must not be blank")
    @URL(message = "BASE_URL must be a valid URL")
    private String baseUrl;

    @NotBlank(message = "ISSUER_ID must not be blank")
    private String issuerId;

    @NotBlank(message = "RESOLVER_BASE_URL must not be blank")
    @URL(message = "RESOLVER_BASE_URL must be a valid URL")
    private String resolverBaseUrl;
}
