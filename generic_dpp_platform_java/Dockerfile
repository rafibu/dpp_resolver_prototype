# Build stage
FROM maven:3.9.11-eclipse-temurin-25 AS build
WORKDIR /app
COPY pom.xml .
RUN mvn dependency:go-offline
COPY src ./src
RUN mvn package -DskipTests

# Run stage
FROM eclipse-temurin:25-jre
WORKDIR /app
COPY --from=build /app/target/*.jar app.jar

# Standard Spring Boot port
EXPOSE 8080

# The application expects the following environment variables at runtime:
# PLATFORM_NAME
# BASE_URL
# ISSUER_ID
# RESOLVER_BASE_URL
# SPRING_DATASOURCE_URL
# SPRING_DATASOURCE_USERNAME
# SPRING_DATASOURCE_PASSWORD

ENTRYPOINT ["java", "-jar", "app.jar"]
