package ch.bfh.dpp_resolver;


import com.google.gson.*;
import com.google.gson.reflect.TypeToken;
import com.google.gson.stream.JsonReader;
import com.google.gson.stream.JsonWriter;
import lombok.extern.slf4j.Slf4j;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.request.AbstractMockHttpServletRequestBuilder;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import java.io.IOException;
import java.lang.reflect.Type;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Base64;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Abstract Parent class of Controller Tests used for integration tests.
 *
 * @author rbu on 16.05.2025
 */
@Slf4j
@ExtendWith(SpringExtension.class)
@SpringBootTest
@TestPropertySource(locations = "classpath:application-test.properties")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@ActiveProfiles(profiles = "test")
public abstract class ControllerTest {
    protected static MockMvc mvc;

    @Autowired
    private WebApplicationContext webappContext;

    @Autowired
    protected TestDatabaseCleaner databaseCleaner;

    @BeforeEach
    public void setup() {
        if (mvc == null) {
            mvc = MockMvcBuilders.webAppContextSetup(webappContext).build();
        }
        databaseCleaner.clean();
    }

    /**
     * !!! This method should only be used if the Deseralization doesn't work properly, always try first with
     * {@link ControllerTest#getResponseAsObject(String, Class)} !!!
     * <p>
     * Uses the MockMvc to perform get on a URL and tries to map it into an Object
     *
     * @param url                      the URL
     * @param clazz                    The Class which the Response should be mapped into
     * @param ignoreObjectMappingError true if normal deserialization throw an error
     * @return An object formed from the Response
     */
    protected <T> T getResponseAsObject(String url, Class<T> clazz, boolean ignoreObjectMappingError) throws Exception {
        return sendRequestAndExpectObject(get(url), clazz, ignoreObjectMappingError);
    }

    /**
     * Sends a GET request to the specified URL and retrieves the response as a byte array.
     *
     * @param url The target URL to which the GET request will be sent.
     * @return A byte array representing the response from the request.
     * @throws Exception If an error occurs during the request or response processing.
     */
    protected byte[] getResponseAsBytes(String url) throws Exception {
        return sendRequestAndExpectString(get(url)).getBytes();
    }

    /**
     * Uses the MockMvc to perform get on a URL and tries to map it into an Object
     *
     * @param url   the URL
     * @param clazz The Class which the Response should be mapped into
     * @return An object formed from the Response
     */
    protected <T> T getResponseAsObject(String url, Class<T> clazz) throws Exception {
        return getResponseAsObject(url, clazz, false);
    }

    /**
     * Uses the MockMvc to perform get on a URL and returns the result as a String
     *
     * @param url the URL
     * @return The Response in the form of a String
     */
    protected String getResponseAsString(String url) throws Exception {
        return sendRequestAndExpectString(get(url));
    }

    /**
     * Uses the MockMvc to perform delete on a URL and returns the result as a String
     *
     * @param url the URL
     * @return The Response in the form of a String
     */
    protected String deleteResponseAsString(String url) throws Exception {
        return deleteResponseAsString(url, null);
    }

    /**
     * ses the MockMvc to perform delete on a URL and returns status of HTTP 204 No Content.
     *
     * @param url the URL
     */
    protected void deleteResponseNoContent(String url) throws Exception {
        sendRequest(delete(url))
                .andExpect(status().isNoContent());
    }

    /**
     * Uses the MockMvc to perform delete on a URL and returns the result as a String
     *
     * @param url  the URL
     * @param body The body, which should be sent with the request (usually JSON)
     * @return The Response in the form of a String
     */
    protected String deleteResponseAsString(String url, String body) throws Exception {
        var deleteRequest = delete(url);
        if (body != null) {
            deleteRequest.content(body).contentType(MediaType.APPLICATION_JSON);
        }
        return sendRequestAndExpectString(deleteRequest);
    }

    /**
     * Uses the MockMvc to perform put on a URL and returns the result as a String
     *
     * @param url  the URL
     * @param body The body, which should be sent with the request (usually JSON)
     * @return The Response in the form of a String
     */
    protected String putResponseAsString(String url, String body) throws Exception {
        var putRequest = put(url);
        if (body != null) {
            putRequest.content(body).contentType(MediaType.APPLICATION_JSON);
        }
        return sendRequestAndExpectString(putRequest);
    }

    /**
     * Uses the MockMvc to perform put on a URL and returns the result as an Object
     *
     * @param url   the URL
     * @param body  The body that should be sent with the request (usually JSON)
     * @param clazz The Class which the Response should be mapped into
     * @return The Response mapped to the specified class
     */
    protected <T> T putResponseAsObject(String url, String body, Class<T> clazz) throws Exception {
        var putRequest = put(url);
        if (body != null) {
            putRequest.content(body).contentType(MediaType.APPLICATION_JSON);
        }
        return sendRequestAndExpectObject(putRequest, clazz);
    }

    /**
     * Sends a PUT request to the current API and expects a certain Status Code Usually used to test erroneous
     * requests, for code 200 use {@link ControllerTest#putResponseAsString(String, String)}
     *
     * @param url        the URL
     * @param body       Body of the request, usually in JSON Form
     * @param statusCode the status code that is expected from {@link HttpStatus}
     */
    protected void putErrorStatusCode(String url, String body, HttpStatus statusCode) throws Exception {
        putErrorStatusCode(url, body, statusCode.value());
    }

    /**
     * Sends a PUT request to the current API and expects a certain Status Code Usually used to test erroneous
     * requests, for code 200 use {@link ControllerTest#putResponseAsString(String, String)}
     *
     * @param url        the URL
     * @param body       Body of the request, usually in JSON Form
     * @param statusCode the status code that is expected (e.g. 400, 403, 500)
     */
    protected void putErrorStatusCode(String url, String body, int statusCode) throws Exception {
        var putRequest = put(url);
        if (body != null) {
            putRequest.content(body).contentType(MediaType.APPLICATION_JSON);
        }
        sendRequest(putRequest)
                .andExpect(status().is(statusCode));
    }

    /**
     * Uses the MockMvc to perform post on a URL and returns the result as a String
     *
     * @param url  the URL
     * @param body The body, which should be sent with the request (usually JSON)
     * @return The Response in the form of a String
     */
    protected String postResponseAsString(String url, String body) throws Exception {
        var postRequest = post(url);
        if (body != null) {
            postRequest.content(body).contentType(MediaType.APPLICATION_JSON);
        }
        return sendRequestAndExpectString(postRequest, HttpStatus.CREATED);
    }

    /**
     * Uses the MockMvc to perform post on a URL and returns the result as a String
     *
     * @param url  the URL
     * @param body The body which should be sent with the request (usually JSON)
     * @return The Response in the form of a String
     */
    protected <T> T postResponseAsObject(String url, String body, Class<T> clazz) throws Exception {
        var postRequest = post(url);
        if (body != null) {
            postRequest.content(body).contentType(MediaType.APPLICATION_JSON);
        }
        return sendRequestAndExpectObject(postRequest, clazz, HttpStatus.CREATED);
    }

    /**
     * Uses the MockMvc to perform post on a URL and returns the result as a String
     *
     * @param url the URL
     * @return The Response in the form of a String
     */
    protected <T> T postResponseAsObject(String url, Class<T> clazz) throws Exception {
        return postResponseAsObject(url, null, clazz);
    }

    /**
     * Uses the MockMvc to perform post on a URL and returns the result as a String
     *
     * @param url the URL
     * @return The Response in the form of a String
     */
    protected String postResponseAsString(String url) throws Exception {
        return postResponseAsString(url, null);
    }

    protected String postFileResponseAsString(String url, MockMultipartFile file) throws Exception {
        return postFileResponseAsString(url, file, HttpStatus.CREATED);
    }

    protected String postFileResponseAsString(String url, MockMultipartFile file, HttpStatus status) throws Exception {
        var multipartRequest = multipart(url).file(file);
        return sendRequestAndExpectString(multipartRequest, status);
    }

    protected <T> T postFileResponseAsObject(String url, MockMultipartFile file, Class<T> clazz,
                                             boolean ignoreObjectMappingError) throws Exception {
        return sendRequestAndExpectObject(multipart(url).file(file), clazz, ignoreObjectMappingError, HttpStatus.CREATED);
    }

    protected <T> T postFileResponseAsObject(String url, MockMultipartFile file, Class<T> clazz)
            throws Exception {
        return postFileResponseAsObject(url, file, clazz, false);
    }

    protected void postFileErrorStatusCode(String url, MockMultipartFile file, HttpStatus statusCode)
            throws Exception {
        postFileErrorStatusCode(url, file, statusCode.value());
    }

    protected void postFileErrorStatusCode(String url, MockMultipartFile file, int statusCode)
            throws Exception {
        sendRequest(multipart(url).file(file))
                .andExpect(status().is(statusCode));
    }

    /**
     * Sends a GET request to the current API and expects a certain Status Code Usually used to test erroneous requests,
     * for code 200 use {@link ControllerTest#getResponseAsString(String)}
     *
     * @param url        the URL
     * @param statusCode the status code which is expected from {@link HttpStatus}
     */
    protected void getErrorStatusCode(String url, HttpStatus statusCode) throws Exception {
        getErrorStatusCode(url, statusCode.value());
    }

    /**
     * Sends a GET request to the current API and expects a certain Status Code Usually used to test erroneous requests,
     * for code 200 use {@link ControllerTest#getResponseAsString(String)}
     *
     * @param url        the URL
     * @param statusCode the status code which is expected (e.g. 400, 403, 500)
     */
    protected void getErrorStatusCode(String url, int statusCode) throws Exception {
        sendRequest(get(url))
                .andExpect(status().is(statusCode));
    }

    /**
     * Sends a POST request to the current API and expects a certain Status Code Usually used to test erroneous
     * requests, for code 201 use {@link ControllerTest#postResponseAsString(String)}
     *
     * @param url        the URL
     * @param statusCode the status code which is expected from {@link HttpStatus}
     */
    protected void postErrorStatusCode(String url, HttpStatus statusCode) throws Exception {
        postErrorStatusCode(url, null, statusCode.value());
    }

    /**
     * Sends a POST request to the current API and expects a certain Status Code Usually used to test erroneous
     * requests, for code 201 use {@link ControllerTest#postResponseAsString(String, String)}
     *
     * @param url        the URL
     * @param body       Body of the request, usually in JSON Form
     * @param statusCode the status code which is expected from {@link HttpStatus}
     */
    protected void postErrorStatusCode(String url, String body, HttpStatus statusCode) throws Exception {
        postErrorStatusCode(url, body, statusCode.value());
    }

    /**
     * Sends a POST request to the current API and expects a certain Status Code Usually used to test erroneous
     * requests, for code 200 use {@link ControllerTest#postResponseAsString(String)}
     *
     * @param url        the URL
     * @param statusCode the status code which is expected (e.g. 400, 403, 500)
     */
    protected void postErrorStatusCode(String url, int statusCode) throws Exception {
        postErrorStatusCode(url, null, statusCode);
    }

    /**
     * Sends a POST request to the current API and expects a certain Status Code Usually used to test erroneous
     * requests, for code 201 use {@link ControllerTest#postResponseAsString(String, String)}
     *
     * @param url        the URL
     * @param body       Body of the request, usually in JSON Form
     * @param statusCode the status code that is expected (e.g. 400, 403, 500)
     */
    protected void postErrorStatusCode(String url, String body, int statusCode) throws Exception {
        var postRequest = post(url);
        if (body != null) {
            postRequest.content(body).contentType(MediaType.APPLICATION_JSON);
        }
        sendRequest(postRequest)
                .andExpect(status().is(statusCode));
    }

    /**
     * Sends a DELETE request to the current API and expects a certain Status Code Usually used to test erroneous
     * requests, for code 200 use {@link ControllerTest#deleteResponseAsString(String)}
     *
     * @param url        the URL
     * @param statusCode the status code which is expected from {@link HttpStatus}
     */
    protected void deleteErrorStatusCode(String url, HttpStatus statusCode) throws Exception {
        deleteErrorStatusCode(url, statusCode.value());
    }

    /**
     * Sends a DELETE request to the current API and expects a certain Status Code Usually used to test erroneous
     * requests, for code 200 use {@link ControllerTest#deleteResponseAsString(String)}
     *
     * @param url        the URL
     * @param statusCode the status code which is expected (e.g. 400, 403, 500)
     */
    protected void deleteErrorStatusCode(String url, int statusCode) throws Exception {
        sendRequest(delete(url))
                .andExpect(status().is(statusCode));
    }

    protected void putBinaryResponseNoContent(String url, byte[] body, MediaType mediaType) throws Exception {
        sendRequest(put(url).content(body).contentType(mediaType))
                .andExpect(status().isNoContent());
    }

    protected ResultActions sendRequest(AbstractMockHttpServletRequestBuilder request) throws Exception {
        return mvc.perform(request);
    }

    private String sendRequestAndExpectString(MockHttpServletRequestBuilder request) throws Exception {
        return sendRequestAndExpectString(request, HttpStatus.OK);
    }

    private <T> T sendRequestAndExpectObject(MockHttpServletRequestBuilder request, Class<T> clazz) throws Exception {
        return sendRequestAndExpectObject(request, clazz, false, HttpStatus.OK);
    }

    private <T> T sendRequestAndExpectObject(MockHttpServletRequestBuilder request, Class<T> clazz, HttpStatus status) throws Exception {
        return sendRequestAndExpectObject(request, clazz, false, status);
    }

    private String sendRequestAndExpectString(AbstractMockHttpServletRequestBuilder request, HttpStatus status) throws Exception {
        return sendRequest(request)
                .andExpect(status().is(status.value()))
                .andReturn().getResponse().getContentAsString();
    }

    private <T> T sendRequestAndExpectObject(AbstractMockHttpServletRequestBuilder request, Class<T> clazz, boolean ignoreObjectMappingError, HttpStatus status) throws Exception {
        return createGson(ignoreObjectMappingError).fromJson(
                sendRequestAndExpectString(request, status), clazz);
    }

    private <T> T sendRequestAndExpectObject(MockHttpServletRequestBuilder request, Class<T> clazz, boolean ignoreObjectMappingError) throws Exception {
        return sendRequestAndExpectObject(request, clazz, ignoreObjectMappingError, HttpStatus.OK);
    }

    /**
     * Creates and configures a {@link Gson} instance for JSON serialization and deserialization.
     * An {@link Instant} type adapter is always registered for proper handling of {@code Instant} objects.
     * If the flag to ignore errors is set to true, additional configurations for leniency
     * and error-tolerant deserialization are applied.
     *
     * @param ignoreError specifies whether the {@link Gson} instance should be lenient and tolerant of
     *                    deserialization failures. If true, leniency and an error-handling type adapter
     *                    factory will be enabled.
     * @return a configured {@link Gson} instance.
     */
    private static Gson createGson(boolean ignoreError) {
        GsonBuilder builder = new GsonBuilder()
                // The whole federation speaks snake_case JSON; map Java camelCase fields onto it.
                .setFieldNamingPolicy(FieldNamingPolicy.LOWER_CASE_WITH_UNDERSCORES)
                .registerTypeAdapter(Instant.class, new InstantTypeAdapter())
                .registerTypeAdapter(LocalDate.class, new LocalDateTypeAdapter())
                .registerTypeAdapter(byte[].class, new ByteArrayTypeAdapter());

        if (ignoreError) {
            builder.setStrictness(Strictness.LENIENT)
                    .registerTypeAdapterFactory(new IgnoreFailureTypeAdapterFactory());
        }
        return builder.create();
    }


    private static class InstantTypeAdapter implements com.google.gson.JsonSerializer<Instant>, JsonDeserializer<Instant> {
        @Override
        public JsonElement serialize(Instant src, Type typeOfSrc, JsonSerializationContext context) {
            return new JsonPrimitive(src.toString());
        }

        @Override
        public Instant deserialize(JsonElement json, Type typeOfT, JsonDeserializationContext context)
                throws JsonParseException {
            return Instant.parse(json.getAsString());
        }
    }

    private static class LocalDateTypeAdapter implements com.google.gson.JsonSerializer<LocalDate>, JsonDeserializer<LocalDate> {
        @Override
        public JsonElement serialize(LocalDate src, Type typeOfSrc, JsonSerializationContext context) {
            return new JsonPrimitive(src.toString());
        }

        @Override
        public LocalDate deserialize(JsonElement json, Type typeOfT, JsonDeserializationContext context)
                throws JsonParseException {
            return LocalDate.parse(json.getAsString());
        }
    }

    private static class ByteArrayTypeAdapter implements JsonSerializer<byte[]>, JsonDeserializer<byte[]> {
        @Override
        public JsonElement serialize(byte[] src, Type typeOfSrc, JsonSerializationContext context) {
            return new JsonPrimitive(Base64.getEncoder().encodeToString(src));
        }

        @Override
        public byte[] deserialize(JsonElement json, Type typeOfT, JsonDeserializationContext context) throws JsonParseException {
            return Base64.getDecoder().decode(json.getAsString());
        }
    }

    private static class IgnoreFailureTypeAdapterFactory implements TypeAdapterFactory {
        public final <T> TypeAdapter<T> create(Gson gson, TypeToken<T> type) {
            final TypeAdapter<T> delegate = gson.getDelegateAdapter(this, type);
            return createCustomTypeAdapter(delegate);
        }

        private <T> TypeAdapter<T> createCustomTypeAdapter(TypeAdapter<T> delegate) {
            return new TypeAdapter<>() {
                @Override
                public void write(JsonWriter out, T value) throws IOException {
                    delegate.write(out, value);
                }

                @Override
                public T read(JsonReader in) throws IOException {
                    try {
                        return delegate.read(in);
                    } catch (Exception e) {
                        in.skipValue();
                        return null;
                    }
                }
            };
        }
    }

}
