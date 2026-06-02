package ch.bfh.dpp_resolver.admin.services;

import ch.bfh.dpp_resolver.admin.dto.PlatformMappingDTO;
import ch.bfh.dpp_resolver.admin.dto.PlatformMigrationRequestDTO;
import ch.bfh.dpp_resolver.admin.models.Platform;
import ch.bfh.dpp_resolver.admin.models.SubjectType;
import ch.bfh.dpp_resolver.admin.repositories.PlatformRepository;
import ch.bfh.dpp_resolver.admin.repositories.SubjectTypeRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Optional;

/**
 * Implements the {@code registerIssuer} and {@code migrate} resolver operations.
 *
 * <p>The resolver registry (Definition 10) maps issuer identifiers to hosting
 * platforms. This service persists and retrieves those mappings through separate
 * command methods: {@link #registerIssuer(PlatformMappingDTO)} creates a new
 * issuer entry, while {@link #migrateIssuer(String, PlatformMigrationRequestDTO)}
 * moves an existing issuer entry to a different hosting platform.</p>
 */
@Service
@RequiredArgsConstructor
public class PlatformMappingService {

    private final PlatformRepository platformRepository;
    private final SubjectTypeRepository subjectTypeRepository;

    @Transactional(readOnly = true)
    public List<PlatformMappingDTO> findAll() {
        return platformRepository.findAll().stream().map(PlatformMappingService::toDTO).toList();
    }

    @Transactional(readOnly = true)
    public List<PlatformMappingDTO> findAllBySubjectType(String subjectTypeName) {
        SubjectType subjectType = subjectTypeRepository.findByName(subjectTypeName).orElseThrow();
        return subjectType.getPlatforms().stream().map(PlatformMappingService::toDTO).toList();
    }

    /**
     * Registers one new issuer-to-platform mapping.
     *
     * <p>The supplied subject types become the issuer's declared subject type set.
     * Existing issuers are rejected so a register call cannot accidentally migrate
     * or modify a live issuer mapping.</p>
     */
    @Transactional
    public PlatformMappingDTO registerIssuer(PlatformMappingDTO platformMappingDTO) {
        Optional<Platform> existing = platformRepository.findByAbbreviation(platformMappingDTO.getIssuerId());
        if (existing.isPresent()) {
            throw new IllegalArgumentException("Issuer already registered, use migrate instead");
        }

        List<SubjectType> subjectTypes = new ArrayList<>(platformMappingDTO.getSubjectTypes().stream()
                .map(st -> subjectTypeRepository.findByName(st).orElseThrow())
                .distinct()
                .toList());

        Platform newPlatform = new Platform();
        mapFromDTO(platformMappingDTO, newPlatform, subjectTypes);
        return toDTO(platformRepository.save(newPlatform));
    }

    /**
     * Migrates an existing issuer to a known target platform.
     *
     * <p>Migration changes only the platform name and resolution URL of the issuer's
     * registry entry. The issuer's subject type set is intentionally preserved so
     * another issuer hosted by the same physical platform cannot contaminate the
     * migrated issuer's acceptance rules.</p>
     */
    @Transactional
    public PlatformMappingDTO migrateIssuer(String issuerId, PlatformMigrationRequestDTO requestDTO) {
        Optional<Platform> existing = platformRepository.findByAbbreviation(issuerId);
        if (existing.isEmpty()) {
            throw new NoSuchElementException("Issuer not registered, use register if it should be added");
        }

        assertPlatformExists(requestDTO.getPlatform(), requestDTO.getNewResolutionUrl());

        Platform platform = existing.get();
        platform.setResolutionUrl(requestDTO.getNewResolutionUrl());
        platform.setPlatformName(requestDTO.getPlatform());
        return toDTO(platformRepository.save(platform));
    }

    private void assertPlatformExists(String platform, String resolutionUrl) {
        List<Platform> found = platformRepository.findByPlatformName(platform);
        if (found.isEmpty()) {
            throw new NoSuchElementException("Platform not registered, use register if it should be added");
        }
        if (found.stream().noneMatch(p -> p.getResolutionUrl().equals(resolutionUrl))) {
            throw new IllegalArgumentException("Platform uses different resolution URL than the one specified in the request");
        }
    }

    private static void mapFromDTO(PlatformMappingDTO dto, Platform entity, List<SubjectType> subjectTypes) {
        entity.setPlatformName(dto.getPlatform());
        entity.setAbbreviation(dto.getIssuerId());
        entity.setResolutionUrl(dto.getResolutionUrl());
        setSubjectTypes(entity, subjectTypes);
    }

    private static void setSubjectTypes(Platform entity, List<SubjectType> subjectTypes) {
        if (entity.getSubjectTypes() == null) {
            entity.setSubjectTypes(new ArrayList<>());
        }

        entity.getSubjectTypes().clear();
        subjectTypes.forEach(subjectType -> {
            entity.getSubjectTypes().add(subjectType);
            if (!subjectType.getPlatforms().contains(entity)) {
                subjectType.getPlatforms().add(entity);
            }
        });
    }

    private static PlatformMappingDTO toDTO(Platform entity) {
        return PlatformMappingDTO.builder()
                .subjectTypes(entity.getSubjectTypes().stream().map(SubjectType::getName).toList())
                .platform(entity.getPlatformName())
                .issuerId(entity.getAbbreviation())
                .resolutionUrl(entity.getResolutionUrl())
                .build();
    }

}
