package ch.bfh.generic_dpp_platform.admin.config;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

import static org.assertj.core.api.Assertions.assertThat;

public class PlatformPropertiesValidationTest {

    private final ApplicationContextRunner contextRunner = new ApplicationContextRunner()
            .withUserConfiguration(TestConfig.class)
            .withBean(LocalValidatorFactoryBean.class);

    @EnableConfigurationProperties(PlatformProperties.class)
    static class TestConfig {}

    @Test
    void whenPropertiesAreMissing_thenContextFails() {
        contextRunner.run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure()).isNotNull();
            // Inspect root cause / message chain in a robust way
            assertThat(context.getStartupFailure().toString() + getFullMessageChain(context.getStartupFailure()))
                    .containsAnyOf("PLATFORM_NAME", "platformName");
        });
    }

    @Test
    void whenUrlIsInvalid_thenContextFails() {
        contextRunner.withPropertyValues(
                "platform.platform-name=Test",
                "platform.base-url=not-a-url",
                "platform.issuer-id=issuer",
                "platform.resolver-base-url=http://valid.com"
        ).run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure()).isNotNull();
            assertThat(context.getStartupFailure().toString() + getFullMessageChain(context.getStartupFailure()))
                    .containsAnyOf("BASE_URL", "baseUrl");
        });
    }

    @Test
    void whenResolverUrlIsInvalid_thenContextFails() {
        contextRunner.withPropertyValues(
                "platform.platform-name=Test",
                "platform.base-url=http://valid.com",
                "platform.issuer-id=issuer",
                "platform.resolver-base-url=not-a-url"
        ).run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure()).isNotNull();
            assertThat(context.getStartupFailure().toString() + getFullMessageChain(context.getStartupFailure()))
                    .containsAnyOf("RESOLVER_BASE_URL", "resolverBaseUrl");
        });
    }

    private String getFullMessageChain(Throwable t) {
        StringBuilder sb = new StringBuilder();
        while (t != null) {
            sb.append(t.getMessage()).append("\n");
            t = t.getCause();
        }
        return sb.toString();
    }

    @Test
    void whenAllPropertiesAreValid_thenContextStarts() {
        contextRunner.withPropertyValues(
                "platform.platform-name=Test",
                "platform.base-url=http://localhost:8081",
                "platform.issuer-id=issuer",
                "platform.resolver-base-url=http://localhost:8080"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            PlatformProperties props = context.getBean(PlatformProperties.class);
            assertThat(props.getPlatformName()).isEqualTo("Test");
        });
    }
}
