package ch.bfh.generic_dpp_platform.dpps.models;

import lombok.Builder;

/**
 * Internal representation of a DPP reference found in a payload.
 * <p>
 * A reference identifies a target logical DPP by subject type and issuer-qualified DPP ID. If {@code version}
 * is present, the reference is hard and identifies a concrete immutable revision. If {@code version} is absent,
 * the reference is soft and identifies only the logical DPP.
 * </p>
 * <p>
 * Hard references must resolve before a new revision is committed. Soft references are informational and are not
 * resolved during issuance or revision.
 * </p>
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
    /**
     * Reference mode inferred from the presence or absence of a concrete revision version.
     */
    public enum DependencyType {
        /**
         * Identifies a concrete immutable revision and must resolve before commit.
         */
        HARD,

        /**
         * Identifies only the logical DPP and is not required to resolve during commit.
         */
        SOFT
    }
}
