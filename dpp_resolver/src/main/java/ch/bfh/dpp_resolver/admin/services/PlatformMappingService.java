package ch.bfh.dpp_resolver.admin.services;

import ch.bfh.dpp_resolver.admin.dto.PlatformMappingDTO;
import ch.bfh.dpp_resolver.admin.models.Platform;
import ch.bfh.dpp_resolver.admin.models.SubjectType;
import ch.bfh.dpp_resolver.admin.repositories.PlatformRepository;
import ch.bfh.dpp_resolver.admin.repositories.SubjectTypeRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.List;

/**
 *
 * @author rbu on 20.04.2026
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

    @Transactional
    public PlatformMappingDTO save(PlatformMappingDTO platformMappingDTO) {
        List<SubjectType> subjectTypes = new ArrayList<>(platformMappingDTO.getSubjectTypes().stream()
                .map(st -> subjectTypeRepository.findByName(st).orElseThrow())
                .toList());

        Platform foundOrNew = platformRepository.findByAbbreviation(platformMappingDTO.getIssuerId()).orElse(new Platform());
        mapFromDTO(platformMappingDTO, foundOrNew, subjectTypes);
        return toDTO(platformRepository.save(foundOrNew));
    }

    private static void mapFromDTO(PlatformMappingDTO dto, Platform entity, List<SubjectType> subjectTypes) {
        entity.setSubjectTypes(subjectTypes);
        entity.setPlatformName(dto.getPlatform());
        entity.setAbbreviation(dto.getIssuerId());
        entity.setResolutionUrl(dto.getResolutionUrl());
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
