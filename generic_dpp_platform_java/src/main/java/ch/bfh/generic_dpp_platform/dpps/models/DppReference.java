package ch.bfh.generic_dpp_platform.dpps.models;

import lombok.Builder;

/**
 * Internal representation of a DPP reference found in a payload.
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
