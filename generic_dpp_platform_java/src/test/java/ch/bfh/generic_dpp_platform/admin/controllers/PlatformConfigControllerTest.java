package ch.bfh.generic_dpp_platform.admin.controllers;

import ch.bfh.generic_dpp_platform.ControllerTest;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

public class PlatformConfigControllerTest extends ControllerTest {

    @Test
    public void testGetPlatformConfig_ShouldReturn404() throws Exception {
        mvc.perform(get("/admin/platform-config"))
                .andExpect(status().isNotFound());
    }

    @Test
    public void testPutPlatformConfig_ShouldReturn404() throws Exception {
        mvc.perform(put("/admin/platform-config")
                        .contentType("application/json")
                        .content("{}"))
                .andExpect(status().isNotFound());
    }
}
