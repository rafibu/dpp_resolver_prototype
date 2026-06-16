package ch.bfh.generic_dpp_platform.admin.services;

import ch.bfh.generic_dpp_platform.admin.dtos.SubjectTypeDTO;
import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.NoSuchElementException;

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

    /**
     * Load a registered subject type as a domain entity for service orchestration.
     * <p>
     * Administrative workflows such as issuer-migration imports are not allowed to invent subject types. They
     * must reuse a subject type that was already registered through the normal subject-type path, just like
     * issue/revise operations do. Returning the entity here keeps those workflows from reaching around the
     * subject-type service directly into the repository.
     * </p>
     *
     * @param name subject type name referenced by an incoming DPP revision
     * @return the persisted subject type entity
     * @throws NoSuchElementException if the subject type is not registered on this platform
     */
    @Transactional(readOnly = true)
    public SubjectType getRequiredSubjectType(String name) {
        return subjectTypeRepository.findByName(name)
                .orElseThrow(() -> new NoSuchElementException("Subject type not found: " + name));
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
