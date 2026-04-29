package ch.bfh.generic_dpp_platform.admin.dtos;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 *
 * @author rbu on 21.04.2026
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class SubjectTypeDTO {
    private String name;
    private String description;
}
