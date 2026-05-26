package ch.bfh.generic_dpp_platform.dpps.models;

import lombok.Builder;

/**
 * Internal representation of a DPP reference found in a payload.
 *
 * @author rbu on 21.04.2026
 */
@Builder
public record DppReference(
        String subjectType,
        String dppId,
        Integer version,
        DependencyType type,
        String originalRef,
        String jsonPath
) {
    public enum DependencyType {
        HARD, SOFT
    }
}
