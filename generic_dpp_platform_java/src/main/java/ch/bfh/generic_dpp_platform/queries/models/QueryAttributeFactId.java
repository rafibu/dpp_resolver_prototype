package ch.bfh.generic_dpp_platform.queries.models;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.Setter;

import java.io.Serial;
import java.io.Serializable;

@Getter
@Setter
@EqualsAndHashCode
@Embeddable
public class QueryAttributeFactId implements Serializable {
    @Serial
    private static final long serialVersionUID = 7578558417971329794L;
    @NotNull
    @Column(name = "logical_dpp_id", nullable = false, length = Integer.MAX_VALUE)
    private String logicalDppId;

    @Size(max = 255)
    @NotNull
    @Column(name = "path", nullable = false)
    private String path;


}