#!/usr/bin/env python3
"""
Uncomfortable Search — deliberately retrieve what's unresolved.

Instead of searching for what you know, search for what you got wrong,
what's still open, what contradicts itself, what you've been avoiding.
The octopus reaches into dark corners.

Usage:
    python3 uncomfortable-search.py              # full scan
    python3 uncomfortable-search.py --topic calcite  # topic-filtered
    python3 uncomfortable-search.py --severity high   # only serious issues

Environment:
    MEMORY_DIR — directory of .md files (default: memory/)

Categories of discomfort:
    🔴 CORRECTIONS  — things you got wrong and were corrected on
    🟡 UNVERIFIED   — claims marked uncertain/unverified/pending
    🟠 OPEN QUESTIONS — explicit questions never answered
    🔵 CONTRADICTIONS — same topic with conflicting information
    ⚪ STALE         — old facts that may need re-checking

Inspired by: Dream 8 — The Crescent Octopus Entity (tentacles reaching
into every dark corner, golden ichor dripping from discomfort, the pink
heart = the emotional core you're avoiding)
"""

import os
import sys
import re
from pathlib import Path
from collections import defaultdict

DEFAULT_MEMORY_DIR = "memory"

# Patterns indicating different types of discomfort
PATTERNS = {
    'corrections': [
        r'(?:corrected|was wrong|mistake|error|actually|not \w+,?\s+but)',
        r'Professor (?:corrected|caught|fixed|pointed out)',
        r'(?:withdrew|retracted|revised|updated from)',
        r'(?:initially|originally) (?:thought|said|called|identified)',
        r'WRONG',
        r'hypothesis withdrawn',
    ],
    'unverified': [
        r'(?:unverified|unconfirmed|uncertain|probably|possibly|maybe)',
        r'(?:pending|needs? (?:verification|confirmation|testing|checking))',
        r'(?:UNVERIFIED|PENDING|TBD|TBC)',
        r'(?:could be|might be|may be|appears to be)',
        r'\?\s*$',  # lines ending with ?
        r'(?:not yet|haven\'t|hasn\'t) (?:confirmed|verified|tested|checked)',
    ],
    'open_questions': [
        r'^\s*[-*]\s*.*\?\s*$',  # bullet points ending with ?
        r'(?:need to|should|must) (?:check|verify|confirm|test|investigate)',
        r'(?:unknown|unclear|ambiguous|disputed)',
        r'(?:QUESTION|TODO|INVESTIGATE|CHECK)',
        r'(?:what|why|how|where|when) (?:is|are|does|did|was|were)',
    ],
    'stale': [
        r'(?:2026-02-\d{2})',  # facts from >3 weeks ago
        r'(?:yesterday|last week|earlier this month)',  # relative time (already stale)
    ],
}

def find_memory_files(memory_dir, topic_filter=None):
    """Find all .md files, optionally filtered by topic."""
    files = []
    md_path = Path(memory_dir)
    
    if md_path.exists():
        for f in md_path.rglob("*.md"):
            if topic_filter:
                try:
                    content = f.read_text(encoding='utf-8', errors='replace').lower()
                    if topic_filter.lower() not in content:
                        continue
                except Exception:
                    continue
            files.append(f)
    
    # Top-level files
    parent = md_path.parent
    for name in ["MEMORY.md", "RECENT.md", "LAST_SESSION.md"]:
        p = parent / name
        if p.exists():
            if topic_filter:
                try:
                    content = p.read_text(encoding='utf-8', errors='replace').lower()
                    if topic_filter.lower() not in content:
                        continue
                except Exception:
                    continue
            files.append(p)
    
    return files

def scan_discomfort(files):
    """Scan files for uncomfortable patterns."""
    findings = defaultdict(list)
    
    for filepath in files:
        try:
            lines = filepath.read_text(encoding='utf-8', errors='replace').split('\n')
        except Exception:
            continue
        
        for i, line in enumerate(lines):
            if not line.strip() or len(line.strip()) < 10:
                continue
            
            for category, patterns in PATTERNS.items():
                for pattern in patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        # Get context
                        start = max(0, i - 1)
                        end = min(len(lines), i + 2)
                        context = '\n'.join(lines[start:end]).strip()
                        
                        findings[category].append({
                            'file': str(filepath),
                            'line': i + 1,
                            'text': line.strip()[:120],
                            'context': context[:200],
                            'pattern': pattern,
                        })
                        break  # one category per line is enough
    
    return findings

def find_contradictions(files):
    """Look for the same topic with conflicting claims."""
    # Extract key claims (simplified: look for "X is Y" patterns)
    claims = defaultdict(list)
    
    for filepath in files:
        try:
            lines = filepath.read_text(encoding='utf-8', errors='replace').split('\n')
        except Exception:
            continue
        
        for i, line in enumerate(lines):
            # Look for identification patterns: "TN### = mineral" or "identified as"
            tn_match = re.search(r'(TN\d+).*?(?:=|identified as|is a?)\s+(\w[\w\s]+)', line, re.IGNORECASE)
            if tn_match:
                specimen = tn_match.group(1)
                identification = tn_match.group(2).strip()[:50]
                claims[specimen].append({
                    'id': identification,
                    'file': str(filepath),
                    'line': i + 1,
                    'text': line.strip()[:100]
                })
    
    # Find specimens with multiple different identifications
    contradictions = []
    for specimen, id_list in claims.items():
        if len(id_list) > 1:
            unique_ids = set(c['id'].lower() for c in id_list)
            if len(unique_ids) > 1:
                contradictions.append({
                    'specimen': specimen,
                    'claims': id_list
                })
    
    return contradictions

def main():
    # Parse args
    topic = None
    severity = None
    
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '--topic' and i + 1 < len(args):
            topic = args[i + 1]
            i += 2
        elif args[i] == '--severity' and i + 1 < len(args):
            severity = args[i + 1]
            i += 2
        else:
            i += 1
    
    memory_dir = os.environ.get('MEMORY_DIR', DEFAULT_MEMORY_DIR)
    files = find_memory_files(memory_dir, topic)
    
    if not files:
        print(f"No files found in {memory_dir}" + (f" matching '{topic}'" if topic else ""))
        sys.exit(1)
    
    print(f"🐙 Uncomfortable Search — scanning {len(files)} files")
    if topic:
        print(f"   Topic filter: {topic}")
    print()
    
    # Scan for discomfort
    findings = scan_discomfort(files)
    
    # Display by category
    category_config = {
        'corrections': ('🔴', 'CORRECTIONS — things you got wrong', 'high'),
        'unverified': ('🟡', 'UNVERIFIED — claims not yet confirmed', 'medium'),
        'open_questions': ('🟠', 'OPEN QUESTIONS — never answered', 'medium'),
        'stale': ('⚪', 'STALE — old facts worth re-checking', 'low'),
    }
    
    total = 0
    for category, (emoji, label, sev) in category_config.items():
        if severity and sev != severity:
            continue
        
        items = findings.get(category, [])
        if not items:
            continue
        
        # Deduplicate by file+line
        seen = set()
        unique = []
        for item in items:
            key = (item['file'], item['line'])
            if key not in seen:
                seen.add(key)
                unique.append(item)
        
        print(f"{emoji} {label} ({len(unique)} found)")
        for item in unique[:8]:
            rel = os.path.relpath(item['file'])
            print(f"   {rel}:{item['line']}")
            print(f"   {item['text']}")
            print()
        
        if len(unique) > 8:
            print(f"   ... and {len(unique) - 8} more\n")
        
        total += len(unique)
    
    # Contradiction check
    if not severity or severity == 'high':
        contradictions = find_contradictions(files)
        if contradictions:
            print(f"🔵 CONTRADICTIONS — same specimen, different IDs ({len(contradictions)} found)")
            for c in contradictions[:5]:
                print(f"   {c['specimen']}:")
                for claim in c['claims']:
                    rel = os.path.relpath(claim['file'])
                    print(f"     → \"{claim['id']}\" ({rel}:{claim['line']})")
                print()
            total += len(contradictions)
    
    # Summary
    print(f"{'='*50}")
    print(f"Total uncomfortable items: {total}")
    if total > 0:
        print(f"\nThe octopus found {total} things hiding in dark corners.")
        print("The golden drip: every unresolved item is a chance to grow.")
    else:
        print("\nEither everything is resolved, or the search needs sharper tentacles.")

if __name__ == '__main__':
    main()
