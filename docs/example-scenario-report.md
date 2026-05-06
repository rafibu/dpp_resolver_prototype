# Scenario S1: Offline Interpretability

**Run ID:** s1-2026-05-03T14-22-11Z
**Started:** 2026-05-03T14:22:11.456Z
**Completed:** 2026-05-03T14:22:35.012Z
**Outcome:** PASSED

## Steps

### Step 1: Setup federation

**Expected:** Federation discovered and reset

**Observed:** Federation ready, PV scenario generated

**Result:** PASSED
**Duration:** 1542.34ms

### Step 2: Cache dependencies on platform-a

**Expected:** PV-module DPP's hard refs resolve and cache

**Observed:** Cache contains 2 entries with verified hashes

**Result:** PASSED
**Duration:** 423.12ms

### Step 3: Verify online resolution works baseline

**Expected:** GET via Resolver returns 200

**Observed:** 200 OK via Resolver

**Result:** PASSED
**Duration:** 156.78ms

### Step 4: Pause platform-b

**Expected:** platform-b becomes unreachable

**Observed:** platform-b unreachable

**Result:** PASSED
**Duration:** 2105.45ms

### Step 5: Validate PV-module closure offline

**Expected:** platform-a serves PV-module from cache

**Observed:** 200 OK from platform-a while platform-b is offline

**Result:** PASSED
**Duration:** 89.12ms

### Step 6: Re-verify hash on cached battery entry

**Expected:** cached payload still hashes to stored hash (I4)

**Observed:** Invariant I4 (Integrity) verified across all reads

**Result:** PASSED
**Duration:** 45.67ms

### Step 7: Resume platform-b

**Expected:** platform-b becomes reachable again

**Observed:** platform-b reachable again (status 200)

**Result:** PASSED
**Duration:** 543.21ms

## Verification of formal-model elements

- **I4 (Integrity)**: All cached hashes verified successfully across all reads. PASSED.
- **I7 (Hard resolvability)**: Closure remained resolvable on cached snapshot after pause. PASSED.

## Conclusion

Scenario S1 demonstrated the offline interpretability property of the architecture. The system successfully resolved the full DPP closure even when one of the participating platforms was offline, thanks to local caching of hard dependencies and integrity verification via hashes.
