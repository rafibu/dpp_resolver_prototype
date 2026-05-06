package ch.bfh.generic_dpp_platform.schemas.schedulers;

import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import ch.bfh.generic_dpp_platform.schemas.connectors.ResolverConnector;
import ch.bfh.generic_dpp_platform.schemas.services.DppSchemaService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;

/**
 *
 * @author rbu on 02.05.2026
 */
@RequiredArgsConstructor
@Component
@Slf4j
public class SchemaCacheUpdateScheduler {

    private final SubjectTypeRepository subjectTypeRepository;
    private final ResolverConnector resolverConnector;

    /**
     * Updates the schema cache for all subject types by fetching them from the Resolver platform.
     */
    @Scheduled(cron = "0 0 0 * * *")
    public void updateSchemaCache() {
        String[] subjectTypes = subjectTypeRepository.findAll().stream()
                .map(SubjectType::getName)
                .toArray(String[]::new);
        log.info("Updating schema cache for {} subject types", subjectTypes.length);
        for (String subjectType : subjectTypes) {
            log.info("Syncing schema for subject type: {}", subjectType);
            resolverConnector.syncSchema(subjectType);
        }
        log.info("Schema cache update finished");
    }
}
