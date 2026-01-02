# Refactoring Opportunities

> **Generated:** 2026-01-02
> **Status:** Pending review

## High Priority

### 1. Generic Exception Usage
- **Location:** 18+ locations (`main.py:87,117,145`, `parse_url.py:131,187`, `tidal.py:207`, `util.py:52`)
- **Issue:** Using generic `Exception()` instead of custom exceptions
- **Fix:** Create custom exception classes (`URLParsingError`, `InvalidMediaTypeError`, etc.)
- **Impact:** High | **Effort:** Medium

### 2. `browse_library_interactive` is 272 lines
- **Location:** `streamrip/rip/main.py:357-629`
- **Issue:** Single function handling library fetching, filtering, pagination, ID mismatch detection, and interactive menu
- **Fix:** Extract into smaller methods:
  - `_fetch_library_albums()`
  - `_filter_downloaded_albums()`
  - `_handle_id_mismatches()`
  - `_paginate_albums()`
  - `_show_interactive_menu()`
- **Impact:** High | **Effort:** High

### 3. Metadata Method Duplication
- **Location:** `streamrip/metadata/*.py`
- **Issue:** 30+ methods like `from_qobuz()`, `from_deezer()`, `from_tidal()`, `from_soundcloud()` with similar patterns
- **Fix:** Create `MetadataFactory` or strategy pattern with single `from_resp(source, resp)` dispatcher
- **Impact:** High (20-30% code reduction) | **Effort:** High

### 4. Embedded Debug Logging
- **Location:** `streamrip/rip/main.py:408-550`
- **Issue:** 140+ lines of debug logging for specific album ID (`eyihaejablvrc`)
- **Fix:** Remove hardcoded checks, create unit tests instead
- **Impact:** Medium | **Effort:** Low

## Medium Priority

### 5. Platform Checks Duplicated
- **Location:** `main.py:30,201,581`
- **Issue:** Same `if platform.system() == "Windows"` check repeated 3x
- **Fix:** Extract `is_windows_platform()` or `get_menu_system()` helper
- **Impact:** Medium | **Effort:** Low

### 6. Hardcoded Magic Numbers
- **Locations:**
  - `main.py:385-387` (fetch_limit = min(500, offset + limit * 3))
  - `tidal.py:162` (pagination limit = 100)
  - `album.py:71` (success_rate = 0.8)
- **Fix:** Create `streamrip/constants.py` with configurable thresholds
- **Impact:** Medium | **Effort:** Low

### 7. Inconsistent Client Method Signatures
- **Location:** `streamrip/client/*.py`
- **Issue:** Different parameter ordering, error handling. `get_user_favorites()` only in Tidal.
- **Fix:** Standardize abstract method signatures in `Client` base class
- **Impact:** Medium | **Effort:** Medium

### 8. Missing Type Hints
- **Location:** `metadata/util.py`, `parse_url.py`
- **Issue:** Functions lack complete type annotations
- **Fix:** Add full type hints to all public methods
- **Impact:** Medium | **Effort:** Low

## Low Priority

### 9. Unaddressed TODO Comments
- **Location:** 12+ TODOs throughout codebase
- **Issue:** Technical debt accumulating
- **Fix:** Create GitHub issues or address them
- **Impact:** Low | **Effort:** Varies

### 10. Assertions vs Exceptions
- **Location:** `db.py:65-67,98-100,118`, `util.py:24`, `qobuz.py:76,68`
- **Issue:** Assertions can be disabled with `-O` flag
- **Fix:** Replace with explicit exception raises
- **Impact:** Medium | **Effort:** Low

---

## Quick Wins (1-2 hours)

1. Extract platform helper (10 mins)
2. Remove debug album tracking code (20 mins)
3. Create constants.py (30 mins)
4. Replace assertions with exceptions (45 mins)
5. Add return type hints (1 hour)

## Action Items

- [ ] Start with quick wins
- [ ] Create custom exceptions module
- [ ] Split `browse_library_interactive`
- [ ] Implement metadata factory pattern
