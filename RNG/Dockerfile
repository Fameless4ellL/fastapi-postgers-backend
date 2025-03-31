FROM maven:3.9.4-eclipse-temurin-17 AS build

WORKDIR /rng

COPY /rng/pom.xml .
COPY /rng/src ./src

# Build
RUN mvn clean package -DskipTests
FROM openjdk:17-jdk-slim

# Set the working directory for the runtime
WORKDIR /rng

# Copy the built JAR file from the build stage
COPY --from=build /rng/target/rng-0.0.1-SNAPSHOT.jar rng.jar

EXPOSE 8001

ENTRYPOINT ["java", "-jar", "rng.jar", "--server.port=8001"]