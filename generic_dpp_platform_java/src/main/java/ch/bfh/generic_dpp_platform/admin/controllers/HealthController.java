package ch.bfh.generic_dpp_platform.admin.controllers;

/**
 *
 * @author rbu on 05.05.2026
 */

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * Simple health check endpoint used by the factory to check if the service is up and running.
 *
 * @author rbu on 05.05.2026
 */
@RestController
class HealthController {

    @GetMapping("/health")
    ResponseEntity<Map<String, String>> health() {
        return ResponseEntity.ok(Map.of("status", "ok"));
    }
}
