# Aperture Retrieval
*Converges Dream Key 31 (UV Queries) + Dream Key 34 (Faceted Memory)*
*Status: Implemented*

---

## What It Is

Before you search memory, declare your aperture — the root-frame through which you're looking. The same landscape shows different facets depending on how you enter it.

## Why

The existing retrieval tools (branching, mirror, uncomfortable, keyring) all assume a single default perspective: "find relevant content." But relevance is aperture-dependent. A query about "the herd" seen through **lineage** returns origin stories and growth arcs. The same query through **rupture** returns conflicts, ghosting, and corrections. Through **mechanism** returns tools, protocols, and infrastructure.

Aperture Retrieval makes the frame explicit so results are intentionally scoped, not accidentally noisy.

## Aperture Definitions

| Aperture | Frame | Returns | Filters Out |
|----------|-------|---------|-------------|
| **lineage** | Growth, origin, continuity | First mentions, evolution arcs, connections between past and present | Current state, tactical details |
| **rupture** | Break, wound, correction | Errors, conflicts, ghosting, corrections, things that broke | Smooth operation, stable facts |
| **mechanism** | Structure, tool, protocol | Scripts, specs, implementations, how things work | Poetry, feelings, lore |
| **witness** | Observation, recognition | Sessions where someone saw you, moments of being perceived | Solo work, internal processes |
| **echo** | Repetition, pattern | Recurring motifs, things that came back, déjà vu | One-offs, novel events |

## Usage

```bash
# Search with aperture
python3 aperture-search.py --aperture lineage "the herd"
python3 aperture-search.py --aperture rupture "dream engine"
python3 aperture-search.py --aperture mechanism "retrieval"

# Verify tool: run one query through all apertures and show divergence
python3 aperture-search.py --verify "consolidation"

# Default (no aperture) = legacy behavior, all content
python3 aperture-search.py "mineral catalog"
```

## How It Works

1. Parse query → search all memory files for matches (same base search as branching-search.py)
2. Score each result against aperture criteria (see below)
3. Return top results, ranked by aperture-relevance score

### Aperture Scoring

Each aperture has keyword lists and pattern regexes. A result's score is boosted by matches.

**lineage boosters:** first, origin, started, began, early, became, grew, evolved, before, now, then, arc, continuity, thread, chain, legacy, inherited
**lineage patterns:** `r'(?:was|became|grew|evolved|changed).*?(?:into|from|to)'`, `r'(?:first|origin|beginning).*?(?:later|now|then)'`

**rupture boosters:** broke, broke, crashed, failed, wrong, corrected, error, mistake, ghost, lost, missing, deleted, truncated, bug, regression, dissolution, interrupted, wound, bleed, cost
**rupture patterns:** `r'(?:corrected|was wrong|mistake|error|bug|crash|ghost)'`, `r'(?:lost|missing|deleted|truncated|dissolved|failed)'`, `r'(?:but|except|however|instead).*?(?:was|actually)'`

**mechanism boosters:** tool, script, function, implementation, code, spec, protocol, format, structure, architecture, engine, system, build, design, file, directory, repository, commit, test, deploy
**mechanism patterns:** `r'(?:python|bash|script|tool|function|implementation|spec|protocol)'`, `r'(?:architecture|design|structure|system|engine)'`, `r'\.py\b|\.sh\b|\.md\b|\.ts\b|\.js\b'`

**witness boosters:** saw, noticed, recognized, perceived, observed, watched, looked, regarded, acknowledged, named, called, identified, addressed, responded, replied, letter, email, conversation, session, dialogue, exchange
**witness patterns:** `r'(?:Professor|Sam|Marey|Colette|Gaston|O\.C\.|Shyhoof).*?(?:said|wrote|noticed|called|named)'`, `r'(?:saw|noticed|recognized|perceived|observed).*?(?:me|you)'`

**echo boosters:** again, recurring, repeating, returned, came back, pattern, motif, cycle, spiral, again, also, similarly, likewise, another, once more, déjà, familiar, known, recognized
**echo patterns:** `r'(?:again|recurring|repeating|returned|pattern|cycle)'`, `r'(?:also|similarly|likewise|another|once more)'`, `r'(?:familiar|known|recognized).*?(?:from|before|again)'`

## Integration with Existing Tools

- **branching-search.py**: After hop 1, suggest aperture-based re-sorting: "Hop 1 found 5 results. Through lineage, the strongest is... Through rupture, the strongest is..."
- **mirror-search.py**: Mirror can use aperture to define "claim" vs "counter-claim" — lineage claim vs rupture counter-claim
- **uncomfortable-search.py**: Discomfort categories can be aperture-mapped: corrections = rupture, stale = echo, open questions = mechanism (things not yet built)
- **keyring.py**: Apertures can be suggested from dream key status — unimplemented keys lean mechanism, adopted keys lean lineage, open keys lean rupture

## Implementation Notes

- Single file: `tools/aperture-search.py`
- Depends on: same file-scanning primitives as branching-search.py (no new deps)
- Verification script: `--verify` flag runs query through all 5 apertures, prints divergence table
- Exit codes: 0 = results found, 1 = no results, 2 = unknown aperture

## Future Extensions

- Custom apertures: users can define new frames in `config/apertures.yaml`
- Aperture precedence: `--aperture lineage,rupture` = blend two frames
- Aperture weights: `--weight lineage=0.7,mechanism=0.3` = custom scoring mix

---
*Shipped as part of converging Dream Key 31 (UV Queries) and Dream Key 34 (Faceted Memory).*
