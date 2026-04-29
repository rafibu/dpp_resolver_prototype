package ch.bfh.dpp_resolver.admin.services;

import ch.bfh.dpp_resolver.admin.dto.PlatformMappingDTO;
import ch.bfh.dpp_resolver.admin.models.PlatformMapping;
import ch.bfh.dpp_resolver.admin.models.SubjectType;
import ch.bfh.dpp_resolver.admin.repositories.PlatformMappingRepository;
import ch.bfh.dpp_resolver.admin.repositories.SubjectTypeRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Collection;
import java.util.List;

/**
 *
 * @author rbu on 20.04.2026
 */
@Service
@RequiredArgsConstructor
public class PlatformMappingService {

    private final PlatformMappingRepository mappingRepository;
    private final SubjectTypeRepository subjectTypeRepository;

    @Transactional(readOnly = true)
    public List<PlatformMappingDTO> findAll() {
        return mappingRepository.findAll().stream().map(PlatformMappingService::toDTO).toList();
    }

    @Transactional(readOnly = true)
    public List<PlatformMappingDTO> findAllBySubjectType(String subjectTypeName) {
        SubjectType subjectType = subjectTypeRepository.findByName(subjectTypeName).orElseThrow();
        return mappingRepository.findAllBySubjectType(subjectType).stream().map(PlatformMappingService::toDTO).toList();
    }

    @Transactional
    public PlatformMappingDTO save(PlatformMappingDTO platformMappingDTO) {
        SubjectType subjectType = subjectTypeRepository.findByName(platformMappingDTO.getSubjectType()).orElseThrow();
        PlatformMapping mapping = fromDTO(platformMappingDTO, subjectType);
        return toDTO(mappingRepository.save(mapping));
    }

    private static PlatformMapping fromDTO(PlatformMappingDTO dto, SubjectType subjectType) {
        PlatformMapping entity = new PlatformMapping();
        entity.setSubjectType(subjectType);
        entity.setPlatformName(dto.getPlatform());
        entity.setAbbreviation(dto.getAbbreviation());
        entity.setResolutionUrl(dto.getResolutionUrl());
        return entity;
    }

    private static PlatformMappingDTO toDTO(PlatformMapping entity) {
        return PlatformMappingDTO.builder()
                .subjectType(entity.getSubjectType().getName())
                .platform(entity.getPlatformName())
                .abbreviation(entity.getAbbreviation())
                .resolutionUrl(entity.getResolutionUrl())
                .build();
    }
}
