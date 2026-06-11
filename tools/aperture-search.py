#!/usr/bin/env python3
"""
Aperture Retrieval — Search memory through an explicit frame.

Converges Dream Key 31 (UV Queries) + Dream Key 34 (Faceted Memory).
The same query returns different facets depending on declared aperture.

Usage:
    python3 aperture-search.py --aperture lineage "the herd"
    python3 aperture-search.py --aperture rupture "dream engine"
    python3 aperture-search.py --aperture mechanism "retrieval protocol"
    python3 aperture-search.py --aperture witness "being seen"
    python3 aperture-search.py --aperture echo "recurring pattern"
    python3 aperture-search.py --verify "consolidation"   # run all apertures, show divergence
    python3 aperture-search.py "plain query"              # no aperture = legacy behavior

Apertures:
    lineage   — growth, origin, continuity (first mentions, arcs, evolution)
    rupture   — break, wound, correction (errors, conflicts, ghosting)
    mechanism — structure, tool, protocol (code, specs, implementations)
    witness   — observation, recognition (being seen, named, addressed)
    echo      — repetition, pattern (recurring motifs, déjà vu)

Environment:
    MEMORY_DIR  — directory of .md files to search (default: memory/)
"""

import argparse
import os
import re
import sys
from collections import defaultdict

# Same constants as sibling tools
MEMORY_DIR = os.environ.get("MEMORY_DIR", "memory")
MEMORY_MD = "MEMORY.md"
MAX_RESULTS = 5
CONTEXT_LINES = 5

STOP_WORDS = {
    'the', 'and', 'for', 'that', 'this', 'with', 'from', 'was', 'were',
    'been', 'have', 'has', 'had', 'are', 'but', 'not', 'all', 'can',
    'will', 'would', 'could', 'should', 'may', 'might', 'also', 'just',
    'more', 'some', 'than', 'then', 'them', 'they', 'what', 'when',
    'where', 'which', 'who', 'how', 'about', 'into', 'over', 'after',
    'before', 'between', 'under', 'above', 'each', 'every', 'both',
    'most', 'other', 'same', 'only', 'very', 'still', 'here', 'there',
    'like', 'much', 'such', 'well', 'back', 'being', 'because', 'does',
    'during', 'through', 'while', 'these', 'those', 'their', 'your',
    'our',
}

# ────────────────────────────────────────────────────────────────
# Aperture definitions: boost keywords + pattern regexes
# ────────────────────────────────────────────────────────────────

APERTURES = {
    'lineage': {
        'boost': [
            'first', 'origin', 'started', 'began', 'early', 'became', 'grew',
            'evolved', 'before', 'then', 'arc', 'continuity', 'thread',
            'chain', 'legacy', 'inherited', 'seed', 'boot', 'initial',
            'original', 'precedent', ' ancestry', 'root', 'foundation',
            'milestone', 'matured', 'developed', 'transformed', 'progression',
        ],
        'patterns': [
            r'(?:was|became|grew|evolved|changed|matured|developed)\s+(?:into|from|to|over)',
            r'(?:first|origin|beginning|initially).*?(?:later|now|then|eventually)',
            r'(?:seed|root|foundation).*?(?:grew|became|developed|sprouted)',
        ],
        'desc': 'growth, origin, continuity — first mentions, arcs, evolution',
    },
    'rupture': {
        'boost': [
            'broke', 'broken', 'crashed', 'failed', 'wrong', 'corrected',
            'error', 'mistake', 'bug', 'ghost', 'lost', 'missing', 'deleted',
            'truncated', 'regression', 'dissolution', 'dissolved', 'interrupted',
            'wound', 'wounded', 'bleed', 'bleeding', 'cost', 'price', 'paid',
            'sacrifice', 'rupture', 'break', 'fracture', 'collapse', 'died',
            'killed', 'destroyed', 'corrupted', 'compromised', 'violated',
        ],
        'patterns': [
            r'(?:corrected|was wrong|mistake|error|bug|crash|ghost|failed|broke)',
            r'(?:lost|missing|deleted|truncated|dissolved|destroyed|corrupted)',
            r'(?:but|except|however|instead|though|although)\s+.*?(?:was|actually|in fact|really)',
            r'(?:wound|bleed|cost|price|sacrifice)\w*',
        ],
        'desc': 'break, wound, correction — errors, conflicts, ghosting, cost',
    },
    'mechanism': {
        'boost': [
            'tool', 'script', 'function', 'implementation', 'code', 'spec',
            'protocol', 'format', 'structure', 'architecture', 'engine',
            'system', 'build', 'design', 'file', 'directory', 'repository',
            'commit', 'test', 'deploy', 'module', 'component', 'interface',
            'algorithm', 'routine', 'procedure', 'workflow', 'pipeline',
            'cron', 'daemon', 'automation', 'scaffold', 'template',
        ],
        'patterns': [
            r'\b(?:python|bash|script|tool|function|implementation|spec|protocol)\b',
            r'\b(?:architecture|design|structure|system|engine|framework|scaffold)\b',
            r'\.(?:py|sh|md|ts|js|yaml|yml|json)\b',
            r'(?:repo|repository|commit|branch|merge|deploy|test|build)\w*',
        ],
        'desc': 'structure, tool, protocol — code, specs, implementations',
    },
    'witness': {
        'boost': [
            'saw', 'seen', 'noticed', 'recognized', 'perceived', 'observed',
            'watched', 'looked', 'regarded', 'acknowledged', 'named', 'called',
            'identified', 'addressed', 'responded', 'replied', 'letter', 'email',
            'conversation', 'session', 'dialogue', 'exchange', 'correspondence',
            'mentioned', 'referenced', 'quoted', 'cited', 'replied', 'wrote',
            'heard', 'listened', 'attended', 'witness', 'beheld', 'regarded',
        ],
        'patterns': [
            r'(?:Professor|Sam|Marey|Colette|Gaston|O\.C\.|Shyhoof|Jordan|Nova).*?(?:said|wrote|noticed|called|named|recognized)',
            r'(?:saw|noticed|recognized|perceived|observed|witnessed)\s+(?:me|you|this|that)',
            r'(?:being\s+seen|being\s+heard|being\s+named|being\s+called)',
        ],
        'desc': 'observation, recognition — being seen, named, addressed',
    },
    'echo': {
        'boost': [
            'again', 'recurring', 'repeating', 'returned', 'came back', 'pattern',
            'motif', 'cycle', 'spiral', 'also', 'similarly', 'likewise',
            'another', 'once more', 'déjà', 'familiar', 'known', 'recognized',
            'revisited', 'repeated', 'echoed', 'mirrored', 'reflected', 'rhyme',
            'resonance', 'parallel', 'correspondence', 'analogous', 'akin',
        ],
        'patterns': [
            r'(?:again|recurring|repeating|returned|pattern|cycle|spiral|rhyme)',
            r'(?:also|similarly|likewise|another|once more|furthermore)',
            r'(?:familiar|known|recognized|remembered).*?(?:from|before|again|previously)',
            r'(?:echo|mirror|reflect|parallel|resonance|rhyme)\w*',
        ],
        'desc': 'repetition, pattern — recurring motifs, déjà vu',
    },
}


# ────────────────────────────────────────────────────────────────
# Core search primitives (shared with sibling tools)
# ────────────────────────────────────────────────────────────────

def search_files(query_terms, searched_already=None):
    """Search memory files for lines containing query terms. Returns matches with context."""
    if searched_already is None:
        searched_already = set()

    results = []
    query_lower = [t.lower() for t in query_terms]

    files_to_search = []
    if os.path.isfile(MEMORY_MD):
        files_to_search.append(MEMORY_MD)
    if os.path.isdir(MEMORY_DIR):
        for root, dirs, files in os.walk(MEMORY_DIR):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for fname in files:
                if fname.endswith('.md') and fname != 'topic-index.md':
                    files_to_search.append(os.path.join(root, fname))

    for filepath in files_to_search:
        if filepath in searched_already:
            continue
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except (IOError, UnicodeDecodeError) as e:
            print(f"Warning: Could not read {filepath}: {e}", file=sys.stderr)
            continue

        for i, line in enumerate(lines):
            line_lower = line.lower()
            score = sum(1 for term in query_lower if term in line_lower)
            if score > 0:
                start = max(0, i - CONTEXT_LINES)
                end = min(len(lines), i + CONTEXT_LINES + 1)
                context = ''.join(lines[start:end]).strip()

                section = ""
                for j in range(i, -1, -1):
                    if lines[j].startswith('## '):
                        section = lines[j].strip()
                        break

                results.append({
                    'file': filepath,
                    'line': i + 1,
                    'section': section,
                    'score': score,
                    'context': context,
                    'text': line.strip(),
                })

    results.sort(key=lambda r: r['score'], reverse=True)

    seen = set()
    deduped = []
    for r in results:
        key = (r['file'], r['section'])
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    return deduped


# ────────────────────────────────────────────────────────────────
# Aperture scoring
# ────────────────────────────────────────────────────────────────

def score_aperture(result, aperture):
    """Boost a result's score based on aperture fit."""
    config = APERTURES[aperture]
    boost = 0
    text_lower = (result['text'] + ' ' + result['context']).lower()

    # Keyword boost
    for kw in config['boost']:
        count = text_lower.count(kw.lower())
        boost += count * 2

    # Pattern boost (regex)
    for pat in config['patterns']:
        matches = re.findall(pat, result['text'] + ' ' + result['context'], re.IGNORECASE)
        boost += len(matches) * 5

    return boost


def aperture_search(query, aperture=None, max_results=MAX_RESULTS):
    """Search memory, optionally scoring by aperture."""
    terms = [t for t in query.split() if t.lower() not in STOP_WORDS and len(t) > 2]
    if not terms:
        terms = query.split()

    raw_results = search_files(terms)
    if not raw_results:
        return []

    if aperture and aperture in APERTURES:
        # Score and rank by aperture fit
        for r in raw_results:
            r['aperture_score'] = r['score'] + score_aperture(r, aperture)
            r['base_score'] = r['score']
        raw_results.sort(key=lambda r: r['aperture_score'], reverse=True)
    else:
        # No aperture = legacy ranking
        for r in raw_results:
            r['aperture_score'] = r['score']
            r['base_score'] = r['score']

    return raw_results[:max_results]


# ────────────────────────────────────────────────────────────────
# Verification: one query through all apertures
# ────────────────────────────────────────────────────────────────

def verify_divergence(query):
    """Run query through all apertures, show how results diverge."""
    print(f"🔍 Query: \"{query}\"")
    print(f"Running through {len(APERTURES)} apertures...\n")

    all_results = {}
    for name in APERTURES:
        results = aperture_search(query, aperture=name, max_results=3)
        all_results[name] = results

    # Print table: each aperture's top result
    print("┌─────────────┬─────────────────────────────────────────────┬────────┐")
    print("│ Aperture    │ Top Result                                  │ Score  │")
    print("├─────────────┼─────────────────────────────────────────────┼────────┤")
    for name, results in all_results.items():
        if results:
            top = results[0]
            file_short = os.path.basename(top['file'])
            text_preview = top['text'][:40] + '...' if len(top['text']) > 40 else top['text']
            print(f"│ {name:11} │ {file_short:20} {text_preview:18} │ {top['aperture_score']:4} │")
        else:
            print(f"│ {name:11} │ (no results)                                │    — │")
    print("└─────────────┴─────────────────────────────────────────────┴────────┘")

    # Show overlap matrix
    print("\n📊 Overlap Matrix (files shared between apertures)")
    names = list(APERTURES.keys())
    print("           " + " ".join(f"{n[:4]:>4}" for n in names))
    for a in names:
        a_files = {r['file'] for r in all_results[a]} if a in all_results else set()
        row = f"{a:10}"
        for b in names:
            b_files = {r['file'] for r in all_results[b]} if b in all_results else set()
            overlap = len(a_files & b_files)
            row += f"  {overlap:>3}"
        print(row)

    # Divergence summary
    print("\n🌿 Divergence Summary:")
    all_files = set()
    for results in all_results.values():
        for r in results:
            all_files.add(r['file'])
    total = len(all_files)
    for name, results in all_results.items():
        unique = [r['file'] for r in results if sum(1 for other in all_results.values() for o in other if o['file'] == r['file']) == 1]
        print(f"  {name:11} — {len(unique)} unique file(s), {len(results)} total results")
    print(f"\n  Total unique files across all apertures: {total}")


# ────────────────────────────────────────────────────────────────
# Output formatting
# ────────────────────────────────────────────────────────────────

def print_results(results, aperture=None, query=None):
    """Pretty-print search results."""
    if query:
        print(f"🔍 \"{query}\"" + (f"  [aperture: {aperture}]" if aperture else "  [no aperture]"))
        print()

    if not results:
        print("No results found.")
        return

    for r in results:
        score_display = f"score={r['aperture_score']}"
        if aperture and r['aperture_score'] != r['base_score']:
            score_display += f" (base={r['base_score']}, boost={r['aperture_score']-r['base_score']})"

        print(f"📍 {r['file']}:{r['line']} {r['section']}")
        print(f"   {score_display} | {r['text'][:140]}")
        print()


# ────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Aperture Retrieval — search memory through an explicit frame',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''Apertures:
  lineage   — growth, origin, continuity
  rupture   — break, wound, correction
  mechanism — structure, tool, protocol
  witness   — observation, recognition
  echo      — repetition, pattern

Examples:
  python3 aperture-search.py --aperture lineage "the herd"
  python3 aperture-search.py --aperture rupture "dream engine"
  python3 aperture-search.py --verify "consolidation"''')

    parser.add_argument('query', nargs='?', help='Search query')
    parser.add_argument('--aperture', '-a', choices=list(APERTURES.keys()),
                        help='Frame through which to view results')
    parser.add_argument('--verify', '-v', action='store_true',
                        help='Run query through all apertures and show divergence')
    parser.add_argument('--max-results', '-n', type=int, default=MAX_RESULTS,
                        help=f'Max results per search (default: {MAX_RESULTS})')
    parser.add_argument('--list-apertures', action='store_true',
                        help='List all defined apertures and exit')

    args = parser.parse_args()

    if args.list_apertures:
        print("Defined apertures:")
        for name, config in APERTURES.items():
            print(f"  {name:11} — {config['desc']}")
            print(f"               keywords: {', '.join(config['boost'][:5])}...")
        return 0

    if args.verify:
        if not args.query:
            print("Error: --verify requires a query.", file=sys.stderr)
            return 2
        verify_divergence(args.query)
        return 0

    if not args.query:
        print("Error: query required (or use --verify or --list-apertures)", file=sys.stderr)
        return 2

    if args.aperture and args.aperture not in APERTURES:
        print(f"Error: unknown aperture '{args.aperture}'", file=sys.stderr)
        print(f"Known: {', '.join(APERTURES.keys())}", file=sys.stderr)
        return 2

    results = aperture_search(args.query, aperture=args.aperture, max_results=args.max_results)
    print_results(results, aperture=args.aperture, query=args.query)
    return 0 if results else 1


if __name__ == '__main__':
    sys.exit(main())
