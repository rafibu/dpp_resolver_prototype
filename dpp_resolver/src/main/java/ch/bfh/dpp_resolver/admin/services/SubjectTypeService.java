package ch.bfh.dpp_resolver.admin.services;

import ch.bfh.dpp_resolver.admin.dto.SubjectTypeDTO;
import ch.bfh.dpp_resolver.admin.models.SubjectType;
import ch.bfh.dpp_resolver.admin.repositories.SubjectTypeRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 *
 * @author rbu on 17.04.2026
 */
@Service
@RequiredArgsConstructor
public class SubjectTypeService {

    private final SubjectTypeRepository subjectTypeRepository;

    @Transactional(readOnly = true)
    public SubjectTypeDTO[] findAll() {
        return subjectTypeRepository.findAll().stream().map(SubjectTypeService::toDTO).toArray(SubjectTypeDTO[]::new);
    }

    @Transactional
    public void save(SubjectTypeDTO dto) {
        if (subjectTypeRepository.existsByName(dto.getName())) {
            throw new IllegalArgumentException("SubjectType already exists");
        }
        subjectTypeRepository.save(mapFromDTO(dto));
    }

    private static SubjectType mapFromDTO(SubjectTypeDTO dto) {
        var st = new SubjectType();
        st.setName(dto.getName());
        st.setDescription(dto.getDescription());
        return st;
    }

    private static SubjectTypeDTO toDTO(SubjectType st) {
        return new SubjectTypeDTO(st.getName(), st.getDescription());
    }
}
