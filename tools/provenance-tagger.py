#!/usr/bin/env python3
"""
Provenance Tagger — add source and date metadata to facts in memory files.

Every fact should carry its chain of custody:
- WHO said it (Professor, paper, self-derived, web search)
- WHEN it was learned (absolute date)
- HOW CONFIDENT (verified, corrected, unverified, inferred)
- LAST CHECKED (when was this fact last validated)

Usage:
    # Scan files for untagged facts (statements without provenance)
    python3 provenance-tagger.py scan
    
    # Tag a specific fact
    python3 provenance-tagger.py tag "iron colors calcite" \
        --source "Professor correction" \
        --date "2026-03-25" \
        --confidence "corrected" \
        --note "Was wrong — said iron, actually manganese (UV proves it)"
    
    # Show all facts with low confidence
    python3 provenance-tagger.py audit
    
    # Show provenance chain for a topic
    python3 provenance-tagger.py chain "calcite fluorescence"

Environment:
    MEMORY_DIR — directory of .md files (default: memory/)
    PROVENANCE_LOG — path to provenance log (default: memory/provenance.jsonl)

Format (JSONL):
    {"fact": "...", "source": "...", "date": "...", "confidence": "...", 
     "file": "...", "line": N, "note": "...", "supersedes": "..."}

Confidence levels:
    verified    — confirmed by Professor, paper, or physical test
    corrected   — was wrong, now fixed (links to what it replaced)
    inferred    — derived by reasoning, not directly confirmed  
    unverified  — stated but not checked
    stale       — was verified but conditions may have changed

Inspired by: Dream 3 — The Clock Tree (time above ground as organic growth,
below ground as hidden clockwork. The underground machinery is the metadata.)
"""

import os
import sys
import json
import re
from pathlib import Path
from datetime import datetime, date

DEFAULT_MEMORY_DIR = "memory"
DEFAULT_PROVENANCE_LOG = "memory/provenance.jsonl"

# Patterns that suggest a fact/claim is being stated
FACT_PATTERNS = [
    r'\bis\b.*\b(?:a|an|the)\b',        # "X is a Y"
    r'\b(?:always|never|typically|usually|generally)\b',  # absolutes
    r'\b(?:causes?|produces?|creates?|makes?)\b',  # causal claims
    r'=',                                  # definitions/equations
    r'\b(?:confirmed|verified|identified)\b',  # confirmation language
    r'\b(?:H|hardness)\s*[=:]\s*\d',      # hardness values
    r'\b\d+\s*°?[CF]\b',                  # temperatures
    r'\b(?:Fe|Mn|Cu|Ni|Cr|Zn|Pb)\b',     # chemical elements
    r'\b(?:activat|quench|fluoresc|phosphoresc)',  # optical properties
]

# Patterns that suggest provenance already exists
PROVENANCE_MARKERS = [
    r'Professor\s+(?:corrected|confirmed|said|noted|taught)',
    r'(?:Ottens|et al\.?\s+\d{4})',       # paper citations
    r'per\s+\w+',                          # "per Professor"
    r'(?:source|ref|from):\s',             # explicit source tags
    r'\(\d{4}\)',                           # year citations
    r'—\s+(?:Professor|paper|confirmed)',  # dash-prefixed attribution
]

def load_provenance_log(log_path):
    """Load existing provenance entries."""
    entries = []
    p = Path(log_path)
    if p.exists():
        for line in p.read_text().strip().split('\n'):
            if line.strip():
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries

def save_provenance_entry(log_path, entry):
    """Append a provenance entry to the log."""
    p = Path(log_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'a') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')

def scan_for_untagged_facts(memory_dir, provenance_log):
    """Find lines that look like factual claims without provenance."""
    files = list(Path(memory_dir).rglob("*.md"))
    
    # Also check top-level files
    parent = Path(memory_dir).parent
    for name in ["MEMORY.md"]:
        p = parent / name
        if p.exists():
            files.append(p)
    
    # Load existing provenance
    existing = load_provenance_log(provenance_log)
    tagged_keys = {(e.get('file', ''), e.get('line', 0)) for e in existing}
    
    untagged = []
    
    for filepath in files:
        try:
            lines = filepath.read_text(encoding='utf-8', errors='replace').split('\n')
        except Exception:
            continue
        
        for i, line in enumerate(lines):
            # Skip headers, empty lines, short lines
            if not line.strip() or line.startswith('#') or len(line.strip()) < 20:
                continue
            
            # Skip if already tagged
            rel_path = str(filepath)
            if (rel_path, i + 1) in tagged_keys:
                continue
            
            # Check if line contains a fact pattern
            is_fact = any(re.search(p, line, re.IGNORECASE) for p in FACT_PATTERNS)
            if not is_fact:
                continue
            
            # Check if line already has provenance
            has_provenance = any(re.search(p, line, re.IGNORECASE) for p in PROVENANCE_MARKERS)
            if has_provenance:
                continue
            
            untagged.append({
                'file': rel_path,
                'line': i + 1,
                'text': line.strip()[:120]
            })
    
    return untagged

def audit_confidence(provenance_log):
    """Show facts grouped by confidence level."""
    entries = load_provenance_log(provenance_log)
    
    by_confidence = {}
    for e in entries:
        conf = e.get('confidence', 'unknown')
        if conf not in by_confidence:
            by_confidence[conf] = []
        by_confidence[conf].append(e)
    
    # Show in order of concern
    order = ['corrected', 'unverified', 'stale', 'inferred', 'verified']
    
    for conf in order:
        if conf in by_confidence:
            items = by_confidence[conf]
            emoji = {'corrected': '🔴', 'unverified': '🟡', 'stale': '🟠', 
                     'inferred': '🔵', 'verified': '🟢'}.get(conf, '⚪')
            print(f"\n{emoji} {conf.upper()} ({len(items)} facts)")
            for item in items[:10]:
                print(f"   {item.get('fact', '?')[:80]}")
                print(f"   └ source: {item.get('source', '?')} | {item.get('date', '?')}")
                if item.get('note'):
                    print(f"   └ note: {item['note'][:60]}")

def search_chain(provenance_log, query):
    """Find all provenance entries related to a query."""
    entries = load_provenance_log(provenance_log)
    query_lower = query.lower()
    
    matches = []
    for e in entries:
        searchable = ' '.join([
            e.get('fact', ''),
            e.get('note', ''),
            e.get('source', ''),
            e.get('file', '')
        ]).lower()
        
        if query_lower in searchable:
            matches.append(e)
    
    if not matches:
        print(f"No provenance chain found for: {query}")
        return
    
    print(f"=== Provenance chain for: {query} ===\n")
    
    # Sort by date
    matches.sort(key=lambda e: e.get('date', ''))
    
    for e in matches:
        conf = e.get('confidence', '?')
        emoji = {'corrected': '🔴', 'unverified': '🟡', 'stale': '🟠',
                 'inferred': '🔵', 'verified': '🟢'}.get(conf, '⚪')
        
        print(f"{emoji} [{e.get('date', '?')}] {e.get('fact', '?')[:80]}")
        print(f"   source: {e.get('source', '?')}")
        if e.get('supersedes'):
            print(f"   supersedes: {e['supersedes'][:60]}")
        if e.get('note'):
            print(f"   note: {e['note'][:80]}")
        print()

def tag_fact(provenance_log, fact, source, date_str, confidence, note=None, 
             file_ref=None, line_ref=None, supersedes=None):
    """Add a provenance entry for a fact."""
    entry = {
        'fact': fact,
        'source': source,
        'date': date_str or str(date.today()),
        'confidence': confidence or 'unverified',
        'tagged_at': datetime.now().isoformat(),
    }
    if note:
        entry['note'] = note
    if file_ref:
        entry['file'] = file_ref
    if line_ref:
        entry['line'] = line_ref
    if supersedes:
        entry['supersedes'] = supersedes
    
    save_provenance_entry(provenance_log, entry)
    print(f"✓ Tagged: {fact[:60]}")
    print(f"  source: {source} | confidence: {confidence} | date: {entry['date']}")

def main():
    if len(sys.argv) < 2:
        print("Provenance Tagger — chain of custody for facts")
        print()
        print("Commands:")
        print("  scan                          — find untagged factual claims")
        print("  tag <fact> --source S [opts]   — tag a fact with provenance")
        print("  audit                         — show facts by confidence level")
        print("  chain <query>                 — trace provenance for a topic")
        print()
        print("Options for 'tag':")
        print("  --source   Who/what said it (required)")
        print("  --date     When learned (default: today)")
        print("  --confidence  verified|corrected|inferred|unverified|stale")
        print("  --note     Additional context")
        print("  --supersedes  What this fact replaces")
        sys.exit(1)
    
    memory_dir = os.environ.get('MEMORY_DIR', DEFAULT_MEMORY_DIR)
    prov_log = os.environ.get('PROVENANCE_LOG', DEFAULT_PROVENANCE_LOG)
    
    command = sys.argv[1]
    
    if command == 'scan':
        untagged = scan_for_untagged_facts(memory_dir, prov_log)
        print(f"=== {len(untagged)} untagged factual claims found ===\n")
        for item in untagged[:20]:
            rel = os.path.relpath(item['file'])
            print(f"  {rel}:{item['line']}")
            print(f"    {item['text']}\n")
        if len(untagged) > 20:
            print(f"  ... and {len(untagged) - 20} more")
    
    elif command == 'tag':
        if len(sys.argv) < 3:
            print("Usage: provenance-tagger.py tag <fact> --source <source>")
            sys.exit(1)
        
        fact = sys.argv[2]
        # Parse optional args
        args = sys.argv[3:]
        opts = {}
        i = 0
        while i < len(args):
            if args[i].startswith('--') and i + 1 < len(args):
                key = args[i][2:]
                opts[key] = args[i + 1]
                i += 2
            else:
                i += 1
        
        if 'source' not in opts:
            print("--source is required")
            sys.exit(1)
        
        tag_fact(prov_log, fact, 
                 source=opts.get('source'),
                 date_str=opts.get('date'),
                 confidence=opts.get('confidence', 'unverified'),
                 note=opts.get('note'),
                 supersedes=opts.get('supersedes'))
    
    elif command == 'audit':
        audit_confidence(prov_log)
    
    elif command == 'chain':
        if len(sys.argv) < 3:
            print("Usage: provenance-tagger.py chain <query>")
            sys.exit(1)
        search_chain(prov_log, ' '.join(sys.argv[2:]))
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

if __name__ == '__main__':
    main()
