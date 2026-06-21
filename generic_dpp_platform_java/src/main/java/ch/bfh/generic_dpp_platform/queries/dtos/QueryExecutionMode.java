package ch.bfh.generic_dpp_platform.queries.dtos;

/**
 * Defines how the query is executed.
 * This is to show how a preprocessed index can be used to speed up the query.
 * Defaults to {@link QueryExecutionMode#INDEXED}.
 */
public enum QueryExecutionMode {
    /**
     * Uses the preprocessed index to find the matching objects
     */
    INDEXED,
    /**
     * Parses for each logical DPP the newest revisions payload
     */
    ON_DEMAND
}
