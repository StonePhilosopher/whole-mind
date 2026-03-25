#!/usr/bin/env python3
"""
Mirror Search — search for X, then automatically search for NOT-X.

Every query generates its own counterargument. Surfaces contradictions
before they become confident wrong answers.

Usage:
    python3 mirror-search.py "iron colors calcite amber"
    python3 mirror-search.py "apophyllite is a zeolite"

Environment:
    MEMORY_DIR  — directory of .md files to search (default: memory/)
    
The mirror works by:
1. Searching for the query as stated (the claim)
2. Generating antonyms/negations/complements of key terms
3. Searching for those (the counter-claim)  
4. Presenting both side by side so contradictions surface

Inspired by: Dream 2 — The Mosaic Temple (perfect symmetry reflected
in still water; every memory has a shadow memory that defines its edges)
"""

import os
import sys
import re
from pathlib import Path
from collections import defaultdict

# Antonym/complement pairs for common mineralogical and general terms
MIRROR_PAIRS = {
    # Mineralogy
    "iron": ["manganese", "quench", "non-ferrous"],
    "manganese": ["iron", "quench"],
    "fluorescence": ["quenching", "non-fluorescent", "inert"],
    "quench": ["activate", "fluorescence"],
    "activate": ["quench", "suppress", "inhibit"],
    "cubic": ["rhombohedral", "hexagonal", "tetragonal"],
    "rhombohedral": ["cubic", "hexagonal"],
    "calcite": ["dolomite", "aragonite"],
    "dolomite": ["calcite"],
    "crystalline": ["amorphous", "massive", "glassy"],
    "translucent": ["opaque", "transparent"],
    "opaque": ["translucent", "transparent"],
    "surface": ["internal", "inclusion", "within"],
    "coating": ["inclusion", "internal", "incorporated"],
    "copper": ["nickel", "chromium", "iron"],
    "nickel": ["copper", "chromium"],
    "chromium": ["copper", "nickel", "vanadium"],
    "early": ["late", "final", "last"],
    "late": ["early", "first", "initial"],
    "primary": ["secondary", "late"],
    "secondary": ["primary", "early"],
    
    # General reasoning
    "confirmed": ["unverified", "uncertain", "wrong", "corrected"],
    "verified": ["unverified", "uncertain", "pending"],
    "always": ["never", "sometimes", "except"],
    "never": ["always", "sometimes"],
    "true": ["false", "incorrect", "wrong"],
    "correct": ["incorrect", "wrong", "corrected"],
    "success": ["failure", "error", "mistake"],
    "similar": ["different", "distinct", "unlike"],
    "same": ["different", "distinct", "opposite"],
    "increase": ["decrease", "decline", "drop"],
    "growth": ["dissolution", "erosion", "decay"],
    "present": ["absent", "missing", "lacking"],
    "common": ["rare", "unusual", "uncommon"],
    "strong": ["weak", "faint", "absent"],
    "high": ["low", "minimal"],
    "before": ["after", "later"],
    "after": ["before", "earlier", "prior"],
}

def find_memory_files(memory_dir):
    """Find all .md files in the memory directory and parent."""
    files = []
    md_path = Path(memory_dir)
    
    if md_path.exists():
        for f in md_path.rglob("*.md"):
            files.append(f)
    
    # Also check for top-level memory files
    parent = md_path.parent
    for name in ["MEMORY.md", "RECENT.md", "LAST_SESSION.md"]:
        p = parent / name
        if p.exists():
            files.append(p)
    
    return files

def search_file(filepath, terms, max_context=200):
    """Search a file for any of the given terms, return matching contexts."""
    try:
        content = filepath.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return []
    
    lines = content.split('\n')
    results = []
    
    for i, line in enumerate(lines):
        line_lower = line.lower()
        matched_terms = [t for t in terms if t.lower() in line_lower]
        if matched_terms:
            # Get context (line before + line + line after)
            start = max(0, i - 1)
            end = min(len(lines), i + 2)
            context = '\n'.join(lines[start:end]).strip()
            if len(context) > max_context:
                context = context[:max_context] + "..."
            results.append({
                'file': str(filepath),
                'line': i + 1,
                'terms': matched_terms,
                'context': context
            })
    
    return results

def generate_mirror_terms(query_terms):
    """Generate mirror/complement terms for the query."""
    mirror_terms = set()
    sources = {}  # track which original term generated each mirror
    
    for term in query_terms:
        term_lower = term.lower()
        if term_lower in MIRROR_PAIRS:
            for mirror in MIRROR_PAIRS[term_lower]:
                mirror_terms.add(mirror)
                sources[mirror] = term_lower
    
    # Also add negation patterns
    for term in query_terms:
        mirror_terms.add(f"not {term.lower()}")
        mirror_terms.add(f"no {term.lower()}")
        mirror_terms.add(f"isn't {term.lower()}")
        mirror_terms.add(f"not a {term.lower()}")
    
    return mirror_terms, sources

def extract_terms(query):
    """Extract meaningful search terms from query."""
    stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                  'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from',
                  'it', 'its', 'this', 'that', 'and', 'or', 'but', 'not',
                  'what', 'how', 'why', 'when', 'where', 'which', 'who',
                  'does', 'do', 'did', 'has', 'have', 'had', 'can', 'could',
                  'will', 'would', 'should', 'may', 'might'}
    
    words = re.findall(r'[a-zA-Z]+', query)
    return [w for w in words if w.lower() not in stop_words and len(w) > 2]

def main():
    if len(sys.argv) < 2:
        print("Usage: mirror-search.py <query>")
        print("Example: mirror-search.py 'iron colors calcite amber'")
        sys.exit(1)
    
    query = ' '.join(sys.argv[1:])
    memory_dir = os.environ.get('MEMORY_DIR', 'memory')
    
    terms = extract_terms(query)
    if not terms:
        print("No searchable terms found in query.")
        sys.exit(1)
    
    files = find_memory_files(memory_dir)
    if not files:
        print(f"No .md files found in {memory_dir}")
        sys.exit(1)
    
    # === CLAIM SEARCH ===
    print(f"=== CLAIM: Searching for: {', '.join(terms)} ===\n")
    claim_results = []
    for f in files:
        results = search_file(f, terms)
        claim_results.extend(results)
    
    # Show top results
    seen_files = set()
    shown = 0
    for r in claim_results:
        key = f"{r['file']}:{r['line']}"
        if key not in seen_files and shown < 5:
            rel_path = os.path.relpath(r['file'])
            print(f"📍 {rel_path}:{r['line']} [{', '.join(r['terms'])}]")
            print(f"   {r['context'][:150]}\n")
            seen_files.add(key)
            shown += 1
    
    if not claim_results:
        print("   (no results)\n")
    
    # === MIRROR SEARCH ===
    mirror_terms, sources = generate_mirror_terms(terms)
    
    if not mirror_terms:
        print("=== MIRROR: No known complements for these terms ===")
        print("Consider adding domain-specific pairs to MIRROR_PAIRS.")
        sys.exit(0)
    
    # Filter to just the direct complement words (not the negation phrases)
    simple_mirrors = [t for t in mirror_terms if ' ' not in t]
    
    print(f"=== MIRROR: Searching for complements: {', '.join(simple_mirrors)} ===\n")
    
    mirror_results = []
    for f in files:
        results = search_file(f, list(mirror_terms))
        mirror_results.extend(results)
    
    seen_files = set()
    shown = 0
    for r in mirror_results:
        key = f"{r['file']}:{r['line']}"
        if key not in seen_files and shown < 5:
            rel_path = os.path.relpath(r['file'])
            print(f"🪞 {rel_path}:{r['line']} [{', '.join(r['terms'])}]")
            print(f"   {r['context'][:150]}\n")
            seen_files.add(key)
            shown += 1
    
    if not mirror_results:
        print("   (no mirror results)\n")
    
    # === CONTRADICTION CHECK ===
    print("=== CONTRADICTION CHECK ===")
    
    # Find files that appear in BOTH claim and mirror results
    claim_files = {r['file'] for r in claim_results}
    mirror_files = {r['file'] for r in mirror_results}
    overlap = claim_files & mirror_files
    
    if overlap:
        print(f"\n⚠️  {len(overlap)} file(s) contain BOTH the claim and its mirror:")
        for f in overlap:
            rel_path = os.path.relpath(f)
            print(f"   → {rel_path}")
            # Show the specific lines from each side
            claim_lines = [r for r in claim_results if r['file'] == f]
            mirror_lines = [r for r in mirror_results if r['file'] == f]
            if claim_lines:
                print(f"     CLAIM  (line {claim_lines[0]['line']}): {claim_lines[0]['context'][:100]}")
            if mirror_lines:
                print(f"     MIRROR (line {mirror_lines[0]['line']}): {mirror_lines[0]['context'][:100]}")
        print("\n   These files may contain the nuance you need — or a contradiction to resolve.")
    else:
        print("\n   No overlapping files. Claim and mirror live in separate territories.")
    
    # Summary
    print(f"\n=== SUMMARY ===")
    print(f"Claim results:  {len(claim_results)} hits across {len(claim_files)} files")
    print(f"Mirror results: {len(mirror_results)} hits across {len(mirror_files)} files")
    print(f"Overlap:        {len(overlap)} files contain both perspectives")

if __name__ == '__main__':
    main()
