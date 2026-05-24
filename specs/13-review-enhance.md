# Post-loop Review / Enhance Mode

## Status: Backlog

Deferred until BAML is stable in production and prototype-mode optimizations are validated.

## Intent

After the agent loop completes all features, the tool can optionally run additional passes:

### Review pass
- Audits vault consistency: every page in `index.md` exists on disk, every referenced entity has a stub, no orphaned decisions.
- Surfaces gaps: acceptance criteria that were never verified, features missing TECH.md, log gaps.
- Produces a `review.md` artifact with scored findings (severity + fix hints).

### Enhance pass
- Re-runs Builder + Verifier on features that passed tests but have rough implementations (e.g., no error handling, missing tests, inconsistent naming).
- Uses a modified prompt that prioritizes polish over new-feature development.
- Respects a `max-enhance-features` limit.

## Configuration sketch

```json
{
  "run": {
    "review": {
      "enabled": false,
      "autoFix": false
    },
    "enhance": {
      "enabled": false,
      "maxFeatures": 5
    }
  }
}
```

Modes: `none` (default), `review`, `enhance`, `both`.

## Dependencies

- BAML migration complete and stable.
- Mapper refactored to support partial/incremental vault updates (Phase 4 optimization).
- Verifier capable of reporting "passes but is rough" vs "passes and is clean".
