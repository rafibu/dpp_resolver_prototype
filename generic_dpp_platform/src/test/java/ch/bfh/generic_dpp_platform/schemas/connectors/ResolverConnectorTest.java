package ch.bfh.generic_dpp_platform.schemas.connectors;

import ch.bfh.generic_dpp_platform.admin.dtos.PlatformConfigDTO;
import ch.bfh.generic_dpp_platform.admin.models.SubjectType;
import ch.bfh.generic_dpp_platform.admin.repositories.SubjectTypeRepository;
import ch.bfh.generic_dpp_platform.admin.services.PlatformConfigService;
import ch.bfh.generic_dpp_platform.schemas.DppSchemaRepository;
import ch.bfh.generic_dpp_platform.schemas.dtos.DppSchemaDTO;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchema;
import ch.bfh.generic_dpp_platform.schemas.models.DppSchemaId;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.web.client.RestTemplate;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class ResolverConnectorTest {

    @Mock
    private PlatformConfigService configService;

    @Mock
    private SubjectTypeRepository subjectTypeRepository;

    @Mock
    private DppSchemaRepository dppSchemaRepository;

    @Mock
    private RestTemplate restTemplate;

    @InjectMocks
    private ResolverConnector resolverConnector;

    private PlatformConfigDTO configDTO;
    private SubjectType subjectType;

    @BeforeEach
    void setUp() {
        configDTO = new PlatformConfigDTO();
        configDTO.setResolverBaseUrl("http://resolver.com");

        subjectType = SubjectType.builder()
                .id(1L)
                .name("TestType")
                .build();
    }

    @Test
    void syncSchema_Success() {
        // Arrange
        String typeName = "TestType";
        when(configService.getPlatformConfig()).thenReturn(configDTO);
        when(subjectTypeRepository.findByName(typeName)).thenReturn(Optional.of(subjectType));

        DppSchemaDTO schema1 = DppSchemaDTO.builder()
                .majorVersion(1)
                .minorVersion(0)
                .publishedAt(Instant.now())
                .schemaDocument(List.of("doc1"))
                .build();
        DppSchemaDTO schema2 = DppSchemaDTO.builder()
                .majorVersion(1)
                .minorVersion(1)
                .publishedAt(Instant.now())
                .schemaDocument(List.of("doc2"))
                .build();

        DppSchemaDTO[] remoteSchemas = {schema1, schema2};
        when(restTemplate.getForObject("http://resolver.com/schemas/" + typeName, DppSchemaDTO[].class))
                .thenReturn(remoteSchemas);

        when(dppSchemaRepository.existsById(any(DppSchemaId.class))).thenReturn(false);

        // Act
        resolverConnector.syncSchema(typeName);

        // Assert
        ArgumentCaptor<List<DppSchema>> captor = ArgumentCaptor.forClass(List.class);
        verify(dppSchemaRepository).saveAll(captor.capture());
        List<DppSchema> savedSchemas = captor.getValue();

        assertEquals(2, savedSchemas.size());
        assertEquals(1, savedSchemas.get(0).getId().getMajorVersion());
        assertEquals(0, savedSchemas.get(0).getId().getMinorVersion());
        assertEquals(1, savedSchemas.get(1).getId().getMinorVersion());
    }

    @Test
    void syncSchema_WithExistingSchemas() {
        // Arrange
        String typeName = "TestType";
        when(configService.getPlatformConfig()).thenReturn(configDTO);
        when(subjectTypeRepository.findByName(typeName)).thenReturn(Optional.of(subjectType));

        DppSchemaDTO schema1 = DppSchemaDTO.builder()
                .majorVersion(1)
                .minorVersion(0)
                .publishedAt(Instant.now())
                .schemaDocument(List.of("doc1"))
                .build();
        DppSchemaDTO schema2 = DppSchemaDTO.builder()
                .majorVersion(1)
                .minorVersion(1)
                .publishedAt(Instant.now())
                .schemaDocument(List.of("doc2"))
                .build();

        DppSchemaDTO[] remoteSchemas = {schema1, schema2};
        when(restTemplate.getForObject("http://resolver.com/schemas/" + typeName, DppSchemaDTO[].class))
                .thenReturn(remoteSchemas);

        // Mock that schema1 already exists, but schema2 does not
        DppSchemaId id1 = DppSchemaId.builder()
                .subjectTypeId(subjectType.getId())
                .majorVersion(1)
                .minorVersion(0)
                .build();
        DppSchemaId id2 = DppSchemaId.builder()
                .subjectTypeId(subjectType.getId())
                .majorVersion(1)
                .minorVersion(1)
                .build();

        when(dppSchemaRepository.existsById(id1)).thenReturn(true);
        when(dppSchemaRepository.existsById(id2)).thenReturn(false);

        // Act
        resolverConnector.syncSchema(typeName);

        // Assert
        ArgumentCaptor<List<DppSchema>> captor = ArgumentCaptor.forClass(List.class);
        verify(dppSchemaRepository).saveAll(captor.capture());
        List<DppSchema> savedSchemas = captor.getValue();

        assertEquals(1, savedSchemas.size());
        assertEquals(1, savedSchemas.get(0).getId().getMajorVersion());
        assertEquals(1, savedSchemas.get(0).getId().getMinorVersion());
    }

    @Test
    void syncSchema_MissingConfig() {
        // Arrange
        configDTO.setResolverBaseUrl(null);
        when(configService.getPlatformConfig()).thenReturn(configDTO);

        // Act & Assert
        assertThrows(IllegalStateException.class, () -> resolverConnector.syncSchema("TestType"));
    }

    @Test
    void syncSchema_MissingSubjectType() {
        // Arrange
        when(configService.getPlatformConfig()).thenReturn(configDTO);
        when(subjectTypeRepository.findByName("Unknown")).thenReturn(Optional.empty());

        // Act & Assert
        assertThrows(IllegalArgumentException.class, () -> resolverConnector.syncSchema("Unknown"));
    }

    @Test
    void syncSchema_NullRemoteSchemas() {
        // Arrange
        String typeName = "TestType";
        when(configService.getPlatformConfig()).thenReturn(configDTO);
        when(subjectTypeRepository.findByName(typeName)).thenReturn(Optional.of(subjectType));
        when(restTemplate.getForObject("http://resolver.com/schemas/" + typeName, DppSchemaDTO[].class))
                .thenReturn(null);

        // Act
        resolverConnector.syncSchema(typeName);

        // Assert
        verify(dppSchemaRepository, never()).saveAll(any());
    }

    @Test
    void syncSchema_EmptyRemoteSchemas() {
        // Arrange
        String typeName = "TestType";
        when(configService.getPlatformConfig()).thenReturn(configDTO);
        when(subjectTypeRepository.findByName(typeName)).thenReturn(Optional.of(subjectType));
        when(restTemplate.getForObject("http://resolver.com/schemas/" + typeName, DppSchemaDTO[].class))
                .thenReturn(new DppSchemaDTO[0]);

        // Act
        resolverConnector.syncSchema(typeName);

        // Assert
        verify(dppSchemaRepository).saveAll(argThat(list -> ((List)list).isEmpty()));
    }
}
