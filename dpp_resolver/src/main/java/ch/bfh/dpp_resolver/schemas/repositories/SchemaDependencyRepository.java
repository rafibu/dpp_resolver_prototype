package ch.bfh.dpp_resolver.schemas.repositories;

import ch.bfh.dpp_resolver.schemas.models.SchemaDependency;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;

public interface SchemaDependencyRepository extends JpaRepository<SchemaDependency, SchemaDependency.SchemaDependencyId> {

    @Query("SELECT sd FROM SchemaDependency sd JOIN FETCH sd.fromSubjectType JOIN FETCH sd.toSubjectType")
    List<SchemaDependency> findAllWithSubjectTypes();
}
