# Generic DPP Platform (Java)

This is a generic implementation of a DPP Platform in Java using Spring Boot.

## Prerequisites
- Java 25
- PostgreSQL database named `dpp_generic_java`

## Configuration
The platform is configured via environment variables. The following variables are required:

| Environment Variable | Description                                         | Example                 |
|----------------------|-----------------------------------------------------|-------------------------|
| `PLATFORM_NAME`      | Name of the platform                                | `Platform A`            |
| `BASE_URL`           | Public base URL of this platform                    | `http://localhost:8081` |
| `ISSUER_ID`          | Identifier used for DPP IDs issued by this platform | `issuerA`               |
| `RESOLVER_BASE_URL`  | Base URL of the DPP Resolver                        | `http://localhost:8080` |

### Database Configuration
| Environment Variable         | Description               | Default                                             |
|------------------------------|---------------------------|-----------------------------------------------------|
| `SPRING_DATASOURCE_URL`      | JDBC URL for the database | `jdbc:postgresql://localhost:5432/dpp_generic_java` |
| `SPRING_DATASOURCE_USERNAME` | Database username         | `postgres`                                          |
| `SPRING_DATASOURCE_PASSWORD` | Database password         | `postgres`                                          |

## Running with Docker
You can run the platform using Docker and providing the environment variables:

```bash
docker run -e PLATFORM_NAME="Platform A" \
           -e BASE_URL="http://localhost:8081" \
           -e ISSUER_ID="issuerA" \
           -e RESOLVER_BASE_URL="http://localhost:8080" \
           -e SPRING_DATASOURCE_URL="jdbc:postgresql://db:5432/dpp_generic_java" \
           -e SPRING_DATASOURCE_USERNAME="postgres" \
           -e SPRING_DATASOURCE_PASSWORD="password" \
           generic-dpp-platform-java
```

## Running locally
Make sure to set the required environment variables before starting the application:

```bash
export PLATFORM_NAME="Generic DPP Platform"
export BASE_URL="http://localhost:8081"
export ISSUER_ID="gendpp"
export RESOLVER_BASE_URL="http://localhost:8080"
./mvnw spring-boot:run
```