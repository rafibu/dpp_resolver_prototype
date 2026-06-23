package ch.bfh.generic_dpp_platform.queries.services;

import ch.bfh.generic_dpp_platform.dpps.models.DppRevision;
import ch.bfh.generic_dpp_platform.dpps.models.LogicalDpp;
import ch.bfh.generic_dpp_platform.queries.models.QueryAttributeFact;
import ch.bfh.generic_dpp_platform.queries.models.QueryAttributeFactId;
import ch.bfh.generic_dpp_platform.queries.repositories.QueryAttributeFactRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.*;

/**
 * Maintains the materialized attribute-fact view used by indexed local queries.
 *
 * <p>For each logical DPP, the service replaces facts from the previous
 * current revision with a flattened projection of the newly issued revision.
 * The index accelerates query evaluation; the revision payload remains the
 * authoritative record.</p>
 */
@Service
@RequiredArgsConstructor
public class MaterializedIndexService {

    private final QueryAttributeFactRepository queryAttributeFactRepository;

    /**
     * Rebuilds one logical DPP's current attribute facts after issue or revise.
     *
     * @param revision the newly stored current revision to project
     */
    @Transactional
    public void createNewMaterializedIndex(DppRevision revision) {
        LogicalDpp dpp = revision.getDpp();

        queryAttributeFactRepository.deleteAllByIdLogicalDppId(dpp.getDppId());

        Map<String, QueryAttributeFact> facts = new LinkedHashMap<>();
        flattenDocument(
                revision.getDppDocument(),
                "",
                dpp,
                facts
        );

        queryAttributeFactRepository.saveAll(facts.values());
    }

    private void flattenDocument(
            Map<String, Object> document,
            String prefix,
            LogicalDpp dpp,
            Map<String, QueryAttributeFact> facts
    ) {
        for (Map.Entry<String, Object> entry : document.entrySet()) {
            String path = prefix.isBlank()
                    ? entry.getKey()
                    : prefix + "." + entry.getKey();

            Object value = entry.getValue();

            if (value instanceof Map<?, ?> nestedMap) {
                flattenNestedMap(nestedMap, path, dpp, facts);
            } else if (value instanceof List<?> list) {
                projectList(path, list, dpp, facts);
            } else {
                addFact(path, value, dpp, facts);
            }
        }
    }

    private void flattenNestedMap(
            Map<?, ?> nestedMap,
            String prefix,
            LogicalDpp dpp,
            Map<String, QueryAttributeFact> facts
    ) {
        for (Map.Entry<?, ?> entry : nestedMap.entrySet()) {
            if (!(entry.getKey() instanceof String key)) {
                continue;
            }

            String path = prefix + "." + key;
            Object value = entry.getValue();

            if (value instanceof Map<?, ?> deeperNestedMap) {
                flattenNestedMap(deeperNestedMap, path, dpp, facts);
            } else if (value instanceof List<?> list) {
                projectList(path, list, dpp, facts);
            } else {
                addFact(path, value, dpp, facts);
            }
        }
    }

    private void projectList(
            String path,
            List<?> list,
            LogicalDpp dpp,
            Map<String, QueryAttributeFact> facts
    ) {
        for (Object item : list) {
            if (item instanceof Map<?, ?> objectItem) {
                projectObjectItem(path, objectItem, dpp, facts);
            } else {
                addFact(path + ".contains_" + normalizePathSegment(String.valueOf(item)), true, dpp, facts);
            }
        }
    }

    private void projectObjectItem(
            String path,
            Map<?, ?> objectItem,
            LogicalDpp dpp,
            Map<String, QueryAttributeFact> facts
    ) {
        List<String> textValues = new LinkedList<>();
        Map<String, Object> scalarValues = new LinkedHashMap<>();

        for (Map.Entry<?, ?> entry : objectItem.entrySet()) {
            if (!(entry.getKey() instanceof String fieldName)) {
                continue;
            }

            Object value = entry.getValue();

            if (value instanceof String textValue && !textValue.isBlank()) {
                textValues.add(normalizePathSegment(textValue));
            } else if (value instanceof Number || value instanceof Boolean) {
                scalarValues.put(normalizePathSegment(fieldName), value);
            } else if (value instanceof Map<?, ?> nestedMap) {
                flattenNestedMap(nestedMap, path + "." + normalizePathSegment(fieldName), dpp, facts);
            } else if (value instanceof List<?> nestedList) {
                projectList(path + "." + normalizePathSegment(fieldName), nestedList, dpp, facts);
            }
        }

        for (String textValue : textValues) {
            addFact(path + ".contains_" + textValue, true, dpp, facts);

            for (Map.Entry<String, Object> scalarValue : scalarValues.entrySet()) {
                String projectedPath = path + "." + textValue + "_" + scalarValue.getKey();
                addFact(projectedPath, scalarValue.getValue(), dpp, facts);
            }
        }
    }

    private String normalizePathSegment(String value) {
        return value.trim()
                .toLowerCase(Locale.ROOT)
                .replaceAll("[^a-z0-9]+", "_")
                .replaceAll("^_+|_+$", "");
    }

    private void addFact(
            String path,
            Object value,
            LogicalDpp dpp,
            Map<String, QueryAttributeFact> facts
    ) {
        createFact(path, value, dpp)
                .ifPresent(fact -> facts.put(factKey(dpp, path), fact));
    }

    private String factKey(LogicalDpp dpp, String path) {
        return dpp.getDppId() + "|" + path;
    }

    private Optional<QueryAttributeFact> createFact(String path, Object value, LogicalDpp dpp) {
        if (value == null || path == null || path.isBlank()) {
            return Optional.empty();
        }

        QueryAttributeFact fact = new QueryAttributeFact();

        QueryAttributeFactId id = new QueryAttributeFactId();
        id.setLogicalDppId(dpp.getDppId());
        id.setPath(path);

        fact.setId(id);
        fact.setLogicalDpp(dpp);
        fact.setSubjectType(dpp.getSubjectType());

        switch (value) {
            case Boolean booleanValue -> fact.setValueBoolean(booleanValue);
            case Number numberValue -> fact.setValueNumber(toBigDecimal(numberValue));
            case String stringValue -> fact.setValueText(stringValue);
            default -> fact.setValueText(String.valueOf(value));
        }

        return Optional.of(fact);
    }

    private BigDecimal toBigDecimal(Number number) {
        if (number instanceof BigDecimal bigDecimal) {
            return bigDecimal;
        }
        return new BigDecimal(number.toString());
    }
}
