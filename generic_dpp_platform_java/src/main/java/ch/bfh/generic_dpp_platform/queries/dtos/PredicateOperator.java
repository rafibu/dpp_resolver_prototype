package ch.bfh.generic_dpp_platform.queries.dtos;

/**
 *
 * @author rbu on 19.06.2026
 */
public enum PredicateOperator {
    /**
     * projected value equals the filter value
     */
    EQ,
    /**
     * projected value exists and differs from the filter value
     */
    NEQ,
    /**
     * at least one non-null projected fact exists for the given path
     */
    EXISTS,
    /**
     * no non-null projected fact exists for the given path
     */
    NOT_EXISTS,
    /**
     * projected value equals one value from a provided list
     */
    IN,
    /**
     * projected numeric value is greater than the filter value
     * This operator is only supported for numeric values or dates
     */
    GT,
    /**
     * projected numeric value is greater than or equal to the filter value
     * This operator is only supported for numeric values or dates
     */
    GTE,
    /**
     * projected numeric value is less than the filter value
     * This operator is only supported for numeric values or dates
     */
    LT,
    /**
     * projected numeric value is less than or equal to the filter value
     * This operator is only supported for numeric values or dates
     */
    LTE;

}
