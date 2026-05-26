package ch.bfh.generic_dpp_platform.dpps.services;

import ch.bfh.generic_dpp_platform.dpps.models.ReferencedDppRevision;
import ch.bfh.generic_dpp_platform.dpps.models.ReferencedDppRevisionId;
import ch.bfh.generic_dpp_platform.dpps.repositories.ReferencedDppRevisionRepository;
import ch.bfh.generic_dpp_platform.dpps.utils.DppUtil;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Arrays;
import java.util.Optional;

/**
 * Service for managing the external DPP revision cache.
 * Implements hash verification on read and 7-day TTL.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class DppRevisionCacheService {

    private final ReferencedDppRevisionRepository repository;

    /**
     * Retrieves a cached revision. Verifies hash integrity and freshness.
     *
     * @param dppId   The DPP ID.
     * @param version The version.
     * @return The cached revision if valid and fresh, otherwise empty.
     */
    @Transactional
    public Optional<ReferencedDppRevision> getCachedRevision(String dppId, Integer version) {
        ReferencedDppRevisionId id = new ReferencedDppRevisionId(dppId, version);
        Optional<ReferencedDppRevision> cached = repository.findById(id);

        if (cached.isEmpty()) {
            return Optional.empty();
        }

        ReferencedDppRevision revision = cached.get();

        // Check if stale (older than 7 days)
        if (revision.getFetchedAt().isBefore(Instant.now().minus(7, ChronoUnit.DAYS))) {
            log.info("Cached revision for {} version {} is stale. Evicting.", dppId, version);
            repository.delete(revision);
            return Optional.empty();
        }

        // Verify hash integrity (Invariant 4)
        byte[] computedHash = DppUtil.hashDocument(revision.getDppDocument());
        if (!Arrays.equals(revision.getHashedDocument(), computedHash)) {
            log.error("Cache integrity violation for {} version {}: expected {}, computed {}. Evicting.",
                    dppId, version, DppUtil.hashToHex(revision.getHashedDocument()), DppUtil.hashToHex(computedHash));
            repository.delete(revision);
            return Optional.empty();
        }

        return Optional.of(revision);
    }

    /**
     * Saves or updates a revision in the cache.
     *
     * @param revision The revision to cache.
     */
    @Transactional
    public void cacheRevision(ReferencedDppRevision revision) {
        revision.setFetchedAt(Instant.now());
        repository.save(revision);
    }

    /**
     * Scheduled job to clean up expired cache entries.
     * Runs daily at midnight.
     */
    @Scheduled(cron = "0 0 0 * * *")
    @Transactional
    public void cleanupExpiredCache() {
        Instant expiryDate = Instant.now().minus(7, ChronoUnit.DAYS);
        repository.deleteByFetchedAtBefore(expiryDate);
        log.info("Cleaned up expired DPP revision cache entries older than {}", expiryDate);
    }
}
