package ch.bfh.generic_dpp_platform.admin.controllers;

import ch.bfh.generic_dpp_platform.admin.dtos.PlatformConfigDTO;
import ch.bfh.generic_dpp_platform.admin.services.PlatformConfigService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 *
 * @author rbu on 21.04.2026
 */
@Slf4j
@RestController
@RequestMapping("/admin/platform-config")
@RequiredArgsConstructor
public class PlatformConfigController {

    private final PlatformConfigService platformConfigService;

    @GetMapping
    public PlatformConfigDTO getPlatformConfig() {
        return platformConfigService.getPlatformConfig();
    }

    @PutMapping
    public PlatformConfigDTO savePlatformConfig(@RequestBody PlatformConfigDTO platformConfigDTO) {
        return platformConfigService.save(platformConfigDTO);
    }
}
