package ch.bfh.generic_dpp_platform.admin.models;

import jakarta.persistence.*;
import lombok.*;

/**
 *
 * @author rbu on 21.04.2026
 */
@Getter
@Setter
@Entity
@Table(name = "platform_config")
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class PlatformConfigEntry {

    @Id
    @Column(name = "config_key", nullable = false)
    private String configKey;

    @Column(name = "config_value", nullable = false)
    private String configValue;
}
