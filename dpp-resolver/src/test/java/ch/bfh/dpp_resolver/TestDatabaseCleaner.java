package ch.bfh.dpp_resolver;

import ch.bfh.dpp_resolver.admin.repositories.PlatformRepository;
import ch.bfh.dpp_resolver.admin.repositories.SubjectTypeRepository;
import ch.bfh.dpp_resolver.schemas.repositories.DppSchemaRepository;
import ch.bfh.dpp_resolver.schemas.repositories.SchemaDependencyRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
public class TestDatabaseCleaner {

    @Autowired
    private PlatformRepository platformRepository;

    @Autowired
    private SubjectTypeRepository subjectTypeRepository;

    @Autowired
    private DppSchemaRepository dppSchemaRepository;

    @Autowired
    private SchemaDependencyRepository schemaDependencyRepository;

    @Transactional
    public void clean() {
        schemaDependencyRepository.deleteAllInBatch();
        dppSchemaRepository.deleteAllInBatch();
        platformRepository.deleteAllInBatch();
        subjectTypeRepository.deleteAllInBatch();
    }
}
