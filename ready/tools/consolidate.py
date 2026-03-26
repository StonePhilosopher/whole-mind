#!/usr/bin/env python3
"""
📦 Consolidation Helper — Review daily notes and suggest promotions

Scans daily notes older than a configurable window and identifies
entries that look worth promoting to MEMORY.md.

Usage:
  python3 consolidate.py                    # scan notes older than 7 days
  python3 consolidate.py --days 3           # scan notes older than 3 days
  python3 consolidate.py --all              # scan all daily notes
  python3 consolidate.py --memory-check     # check MEMORY.md size

Heuristics for promotion candidates:
  - Lines containing "important", "remember", "lesson", "decision", "learned"
  - Lines containing "TODO" or "FIXME" (might be deferred tasks)
  - Lines with emphasis markers (**bold** or CAPS)
  - Lines that mention people by name (likely relationship context)
  - Section headers (## markers) as context for the lines below them

This is a suggestion tool, not an auto-promoter. You decide what to keep.
"""

import os
import sys
import argparse
import re
from datetime import datetime, timedelta
from pathlib import Path


# Promotion signal words (case-insensitive)
SIGNAL_WORDS = [
    'important', 'remember', 'lesson', 'learned', 'decision', 'decided',
    'mistake', 'correction', 'corrected', 'insight', 'realized', 'realized',
    'always', 'never', 'rule', 'principle', 'key fact', 'worth keeping',
    'don\'t forget', 'note to self', 'significant', 'breakthrough',
]

# Deferred task signals
TASK_SIGNALS = ['todo', 'fixme', 'later', 'deferred', 'waiting on', 'blocked']

# Emotional signals (worth preserving per the architecture)
EMOTION_SIGNALS = [
    'beautiful', 'frustrated', 'angry', 'proud', 'sad', 'excited',
    'surprised', 'uncomfortable', 'grateful', 'moved', 'felt like',
]


def find_daily_notes(memory_dir):
    """Find all daily note files matching YYYY-MM-DD.md pattern."""
    notes = []
    for f in Path(memory_dir).glob('*.md'):
        m = re.match(r'(\d{4}-\d{2}-\d{2})\.md$', f.name)
        if m:
            try:
                date = datetime.strptime(m.group(1), '%Y-%m-%d').date()
                notes.append((date, f))
            except ValueError:
                continue
    return sorted(notes, key=lambda x: x[0])


def scan_note(filepath):
    """Scan a daily note for promotion candidates."""
    candidates = []
    current_section = "General"
    
    with open(filepath, 'r') as f:
        for i, line in enumerate(f, 1):
            stripped = line.strip()
            
            # Track section headers
            if stripped.startswith('## '):
                current_section = stripped.lstrip('#').strip()
                continue
            
            if not stripped or stripped.startswith('#'):
                continue
            
            line_lower = stripped.lower()
            reasons = []
            
            # Check signal words
            for word in SIGNAL_WORDS:
                if word in line_lower:
                    reasons.append(f'signal: "{word}"')
                    break
            
            # Check task signals
            for word in TASK_SIGNALS:
                if word in line_lower:
                    reasons.append(f'task: "{word}"')
                    break
            
            # Check emotional signals
            for word in EMOTION_SIGNALS:
                if word in line_lower:
                    reasons.append(f'emotion: "{word}"')
                    break
            
            # Check emphasis
            if '**' in stripped:
                reasons.append('emphasis: **bold**')
            if re.search(r'\b[A-Z]{3,}\b', stripped) and not stripped.startswith('-'):
                reasons.append('emphasis: CAPS')
            
            if reasons:
                candidates.append({
                    'line': i,
                    'section': current_section,
                    'text': stripped[:120],
                    'reasons': reasons,
                })
    
    return candidates


def check_memory_size(workspace_dir):
    """Check MEMORY.md line count and warn if over budget."""
    memory_path = os.path.join(workspace_dir, 'MEMORY.md')
    if not os.path.exists(memory_path):
        print("MEMORY.md not found.")
        return
    
    with open(memory_path, 'r') as f:
        lines = f.readlines()
    
    total = len(lines)
    non_empty = len([l for l in lines if l.strip()])
    
    print(f"📊 MEMORY.md: {total} lines ({non_empty} non-empty)")
    if total > 200:
        print(f"   ⚠️  Over budget ({total}/200). Time to compress or archive.")
    elif total > 150:
        print(f"   🟡 Getting full ({total}/200). Review soon.")
    else:
        print(f"   🟢 Within budget ({total}/200).")


def main():
    parser = argparse.ArgumentParser(description='📦 Consolidation Helper')
    parser.add_argument('--days', type=int, default=7,
                        help='Scan notes older than N days (default: 7)')
    parser.add_argument('--all', action='store_true',
                        help='Scan all daily notes')
    parser.add_argument('--memory-check', action='store_true',
                        help='Check MEMORY.md size')
    parser.add_argument('--workspace', default='.',
                        help='Workspace root directory (default: current)')
    
    args = parser.parse_args()
    
    workspace = os.path.abspath(args.workspace)
    memory_dir = os.path.join(workspace, 'memory')
    
    if args.memory_check:
        check_memory_size(workspace)
        return
    
    if not os.path.isdir(memory_dir):
        print(f"No memory/ directory found at {memory_dir}")
        print("Create it with: mkdir -p memory/")
        sys.exit(1)
    
    notes = find_daily_notes(memory_dir)
    if not notes:
        print("No daily notes found (looking for memory/YYYY-MM-DD.md files)")
        return
    
    today = datetime.now().date()
    cutoff = today - timedelta(days=args.days) if not args.all else None
    
    # Filter notes
    if cutoff:
        scan_notes = [(d, p) for d, p in notes if d <= cutoff]
        print(f"📦 Consolidation scan: notes older than {args.days} days (before {cutoff})")
    else:
        scan_notes = notes
        print(f"📦 Consolidation scan: all {len(notes)} daily notes")
    
    if not scan_notes:
        print(f"No notes to scan. Your oldest note is from {notes[0][0]} ({(today - notes[0][0]).days} days ago).")
        return
    
    print(f"Scanning {len(scan_notes)} notes...\n")
    
    total_candidates = 0
    for date, path in scan_notes:
        candidates = scan_note(path)
        if candidates:
            age = (today - date).days
            print(f"--- {date} ({age} days ago) ---")
            for c in candidates:
                reasons = ', '.join(c['reasons'])
                print(f"  L{c['line']} [{c['section']}] ({reasons})")
                print(f"    {c['text']}")
            print()
            total_candidates += len(candidates)
    
    print(f"---")
    print(f"Found {total_candidates} promotion candidates in {len(scan_notes)} notes.")
    if total_candidates > 0:
        print(f"Review each candidate: promote to MEMORY.md, or let it fade.")
    else:
        print(f"Nothing flagged. Either your notes are clean or the heuristics need tuning.")
    
    # Also check memory size
    print()
    check_memory_size(workspace)


if __name__ == '__main__':
    main()
