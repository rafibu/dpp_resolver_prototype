package ch.bfh.generic_dpp_platform.admin.services;

import ch.bfh.generic_dpp_platform.admin.dtos.PlatformConfigDTO;
import ch.bfh.generic_dpp_platform.admin.models.PlatformConfigEntry;
import ch.bfh.generic_dpp_platform.admin.repositories.PlatformConfigRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 *
 * @author rbu on 21.04.2026
 */
@Service
@RequiredArgsConstructor
public class PlatformConfigService {

    private static final String PLATFORM_NAME = "platform_name";
    private static final String BASE_URL = "base_url";
    private static final String ISSUER_ID = "issuer_id";
    private static final String RESOLVER_BASE_URL = "resolver_base_url";

    private final PlatformConfigRepository configRepository;

    @Transactional(readOnly = true)
    public PlatformConfigDTO getPlatformConfig() {
        List<PlatformConfigEntry> all = configRepository.findAll();
        return toDTO(all);
    }

    @Transactional
    public PlatformConfigDTO save(PlatformConfigDTO platformConfigDTO){
        List<PlatformConfigEntry> entries = fromDTO(platformConfigDTO);
        configRepository.saveAll(entries);
        List<PlatformConfigEntry> all = configRepository.findAll();
        return toDTO(all);
    }

    private static List<PlatformConfigEntry> fromDTO(PlatformConfigDTO platformConfigDTO) {
        List<PlatformConfigEntry> entries = new ArrayList<>(4);
        addIfNotNull(entries, PLATFORM_NAME, platformConfigDTO.getPlatformName());
        addIfNotNull(entries, BASE_URL, platformConfigDTO.getBaseUrl());
        addIfNotNull(entries, ISSUER_ID, platformConfigDTO.getIssuerId());
        addIfNotNull(entries, RESOLVER_BASE_URL, platformConfigDTO.getResolverBaseUrl());
        return entries;
    }

    private static PlatformConfigDTO toDTO(List<PlatformConfigEntry> platformConfigEntries) {
        Map<String, String> valuesByKey = platformConfigEntries.stream()
                .filter(entry -> entry.getConfigValue() != null && !entry.getConfigValue().isBlank())
                .collect(Collectors.toMap(
                        PlatformConfigEntry::getConfigKey,
                        PlatformConfigEntry::getConfigValue,
                        (existing, replacement) -> replacement
                ));

        PlatformConfigDTO dto = new PlatformConfigDTO();
        dto.setPlatformName(valuesByKey.get(PLATFORM_NAME));
        dto.setBaseUrl(valuesByKey.get(BASE_URL));
        dto.setIssuerId(valuesByKey.get(ISSUER_ID));
        dto.setResolverBaseUrl(valuesByKey.get(RESOLVER_BASE_URL));
        return dto;
    }

    private static void addIfNotNull(List<PlatformConfigEntry> list, String key, String value) {
        if (value != null) {
            list.add(entry(key, value));
        }
    }

    private static PlatformConfigEntry entry(String key, String value) {
        return PlatformConfigEntry.builder()
                .configKey(key)
                .configValue(value)
                .build();
    }
}
