package ch.bfh.generic_dpp_platform.admin.services;

import ch.bfh.generic_dpp_platform.admin.dtos.SubjectTypeDTO;
import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

/**
 *
 * @author rbu on 21.04.2026
 */
@Service
@RequiredArgsConstructor
public class SubjectTypeService {
    private final SubjectTypeRepository subjectTypeRepository;

    @Transactional(readOnly = true)
    public List<SubjectTypeDTO> getAllSupportedSubjectTypes() {
        return subjectTypeRepository.findAll().stream().map(SubjectTypeService::toDTO).toList();
    }

    @Transactional
    public SubjectTypeDTO createSubjectType(SubjectTypeDTO subjectTypeDTO) {
        if (subjectTypeRepository.existsByName(subjectTypeDTO.getName())) {
            throw new IllegalArgumentException("Subject type with name " + subjectTypeDTO.getName() + " already exists");
        }
        SubjectType toCreate = fromDTO(subjectTypeDTO);
        return toDTO(subjectTypeRepository.save(toCreate));
    }

    private static SubjectType fromDTO(SubjectTypeDTO subjectTypeDTO) {
        return SubjectType.builder()
                .name(subjectTypeDTO.getName())
                .description(subjectTypeDTO.getDescription())
                .build();
    }

    private static SubjectTypeDTO toDTO(SubjectType subjectType) {
        return SubjectTypeDTO.builder()
                .name(subjectType.getName())
                .description(subjectType.getDescription())
                .build();
    }
}
