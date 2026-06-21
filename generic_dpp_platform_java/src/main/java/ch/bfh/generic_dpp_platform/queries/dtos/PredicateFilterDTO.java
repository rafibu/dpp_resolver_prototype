package ch.bfh.generic_dpp_platform.queries.dtos;

import ch.bfh.generic_dpp_platform.queries.helpers.PredicateQueryHelper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import jakarta.validation.constraints.NotNull;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.util.Collection;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Stream;

/**
 * A single filter to be applied to a predicate query.
 *
 * @author rbu on 19.06.2026
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class PredicateFilterDTO {
    /**
     * The path to the property to filter on.
     * Can be a dot-separated path to nested properties.
     */
    @NotNull
    private String path;

    /**
     * The operator to use for filtering.
     */
    @NotNull
    private PredicateOperator operator;

    /**
     * The value to compare against.
     * The type of the value must match the type of the property being filtered on.
     * for {@link PredicateOperator#EXISTS} and {@link PredicateOperator#NOT_EXISTS} this is ignored.
     */
    private Object value;

    /**
     * Evaluates this filter against the given document.
     * <p>
     * The configured path is resolved against the document and the resulting value is compared
     * with this filter's value using the configured operator.
     * </p>
     *
     * @param document the document to evaluate
     * @return {@code true} if the document satisfies this filter, otherwise {@code false}
     * @throws IllegalArgumentException if the filter cannot be evaluated for the resolved value
     */
    public boolean matches(Map<String, Object> document) {
        Object documentValue = PredicateQueryHelper.resolvePath(document, path);
        try {
            return operatorMatches(documentValue, value);
        } catch (IllegalArgumentException exception) {
            throw new IllegalArgumentException("Invalid filter: " + path + " " + operator + " " + value, exception);
        }
    }

    /**
     * Checks if the given document value satisfies the condition defined by the filter.
     *
     * @param documentValue the value from the document to be evaluated
     * @return {@code true} if the document value meets the condition,
     *         {@code false} otherwise
     */
    public boolean matches(Object documentValue) {
        return operatorMatches(documentValue, value);
    }

    private boolean operatorMatches(Object documentValue, Object predicateValue) {
        return switch (operator) {
            case EQ -> valuesEqual(documentValue, predicateValue);
            case NEQ -> documentValue != null && !valuesEqual(documentValue, predicateValue);
            case IN -> predicateValues(predicateValue)
                    .anyMatch(value -> valuesEqual(documentValue, value));
            case GT -> compare(documentValue, predicateValue) > 0;
            case GTE -> compare(documentValue, predicateValue) >= 0;
            case LT -> compare(documentValue, predicateValue) < 0;
            case LTE -> compare(documentValue, predicateValue) <= 0;
            case EXISTS -> documentValue != null;
            case NOT_EXISTS -> documentValue == null;
        };
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    private int compare(Object documentValue, Object predicateValue) {
        if (documentValue instanceof Number documentNumber && predicateValue != null) {
            try {
                return new BigDecimal(documentNumber.toString())
                        .compareTo(new java.math.BigDecimal(predicateValue.toString()));
            } catch (NumberFormatException exception) {
                throw new IllegalArgumentException(
                        "Value type mismatch: " + documentValue + " vs " + predicateValue,
                        exception);
            }
        }
        if (!(documentValue instanceof Comparable comparable)) {
            throw new IllegalArgumentException("Value is not comparable: " + documentValue);
        }
        try {
            return comparable.compareTo(predicateValue);
        } catch (ClassCastException exception) {
            throw new IllegalArgumentException("Value type mismatch: " + documentValue + " vs " + predicateValue, exception);
        }
    }

    private boolean valuesEqual(Object documentValue, Object predicateValue) {
        if (documentValue instanceof Number documentNumber && predicateValue != null) {
            try {
                return new BigDecimal(documentNumber.toString())
                        .compareTo(new BigDecimal(predicateValue.toString())) == 0;
            } catch (NumberFormatException ignored) {
                return false;
            }
        }
        if (documentValue instanceof Boolean documentBoolean && predicateValue instanceof String stringValue) {
            return (documentBoolean && "true".equalsIgnoreCase(stringValue))
                    || (!documentBoolean && "false".equalsIgnoreCase(stringValue));
        }
        return Objects.equals(documentValue, predicateValue);
    }

    private Stream<?> predicateValues(Object predicateValue) {
        if (predicateValue instanceof Collection<?> collection) {
            return collection.stream();
        }
        if (predicateValue instanceof Object[] values) {
            return Stream.of(values);
        }
        return Stream.empty();
    }
}
