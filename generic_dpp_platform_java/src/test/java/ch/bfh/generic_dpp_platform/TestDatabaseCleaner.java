package ch.bfh.generic_dpp_platform;

import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import ch.bfh.generic_dpp_platform.dpps.repositories.DppRevisionRepository;
import ch.bfh.generic_dpp_platform.dpps.repositories.LogicalDppRepository;
import ch.bfh.generic_dpp_platform.dpps.repositories.ReferencedDppRevisionRepository;
import ch.bfh.generic_dpp_platform.schemas.repositories.DppSchemaRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
public class TestDatabaseCleaner {

    @Autowired
    private DppRevisionRepository dppRevisionRepository;

    @Autowired
    private LogicalDppRepository logicalDppRepository;

    @Autowired
    private ReferencedDppRevisionRepository referencedDppRevisionRepository;

    @Autowired
    private DppSchemaRepository dppSchemaRepository;

    @Autowired
    private SubjectTypeRepository subjectTypeRepository;

    @Transactional
    public void clean() {
        dppRevisionRepository.deleteAllInBatch();
        referencedDppRevisionRepository.deleteAllInBatch();
        logicalDppRepository.deleteAllInBatch();
        dppSchemaRepository.deleteAllInBatch();
        subjectTypeRepository.deleteAllInBatch();
    }
}
