package ch.bfh.generic_dpp_platform;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.http.converter.json.JacksonJsonHttpMessageConverter;
import org.springframework.web.client.RestTemplate;
import tools.jackson.databind.json.JsonMapper;

import java.io.IOException;
import java.net.HttpURLConnection;

@SpringBootApplication
@ConfigurationPropertiesScan
public class GenericDppPlatformApplication {

	static void main(String[] args) {
		SpringApplication.run(GenericDppPlatformApplication.class, args);
	}

	/**
	 * Builds a RestTemplate that (de)serializes JSON with the application's configured
	 * {@link JsonMapper}. A bare {@code new RestTemplate()} would use a default Jackson mapper
	 * that does not pick up {@code spring.jackson.property-naming-strategy=SNAKE_CASE}, so it
	 * would expect camelCase and deserialize snake_case fields such as {@code schema_version}
	 * to null. Reusing the configured snake_case mapper keeps outbound calls (resolver schema
	 * fetch, cross-platform revision fetch for I7) consistent with the rest of the federation.
	 */
	private static RestTemplate withConfiguredJson(RestTemplate restTemplate, JsonMapper jsonMapper) {
		restTemplate.getMessageConverters().addFirst(new JacksonJsonHttpMessageConverter(jsonMapper));
		return restTemplate;
	}

	@Bean
	public RestTemplate restTemplate(JsonMapper jsonMapper) {
		return withConfiguredJson(new RestTemplate(), jsonMapper);
	}

	@Bean(name = "noRedirectRestTemplate")
	public RestTemplate noRedirectRestTemplate(JsonMapper jsonMapper) {
		SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory() {
			@Override
			protected void prepareConnection(HttpURLConnection connection, String httpMethod) throws IOException {
				super.prepareConnection(connection, httpMethod);
				connection.setInstanceFollowRedirects(false);
			}
		};
		return withConfiguredJson(new RestTemplate(factory), jsonMapper);
	}
}
