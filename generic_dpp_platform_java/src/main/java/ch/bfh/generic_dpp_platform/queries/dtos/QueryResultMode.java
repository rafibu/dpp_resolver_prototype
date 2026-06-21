package ch.bfh.generic_dpp_platform.queries.dtos;

/**
 * Defines what kind of result the query sender expects.
 */
public enum QueryResultMode {
    /**
     * Returns matching revision references and optionally selected projected fields.
     */
    SELECT,
    /**
     * Counts the matching revisions in the platform-local candidate set.
     */
    COUNT,
    /**
     * Returns the sum of the values of the specified field.
     */
    SUM
}
