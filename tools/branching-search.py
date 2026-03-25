#!/usr/bin/env python3
"""
Branching Retrieval — Two-hop search across memory files.

Takes an initial query, finds matching content, extracts new keywords
from results, and searches again. Returns merged context from both hops.

Usage:
    python branching-search.py "apophyllite optical effects"
    python branching-search.py "that conversation about consciousness"
"""

import os
import re
import sys
from collections import defaultdict

MEMORY_DIR = os.environ.get("MEMORY_DIR", "memory")
MEMORY_MD = "MEMORY.md"
MAX_RESULTS_PER_HOP = 5
CONTEXT_LINES = 5  # lines before/after a match to include

# Words to skip when extracting branch keywords
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


def search_files(query_terms, searched_already=None):
    """Search memory files for lines containing query terms. Returns matches with context."""
    if searched_already is None:
        searched_already = set()
    
    results = []
    query_lower = [t.lower() for t in query_terms]
    
    # Collect all .md files
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
                # Get context window
                start = max(0, i - CONTEXT_LINES)
                end = min(len(lines), i + CONTEXT_LINES + 1)
                context = ''.join(lines[start:end]).strip()
                
                # Get section header
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
    
    # Sort by score descending, deduplicate by file+section
    results.sort(key=lambda r: r['score'], reverse=True)
    
    seen = set()
    deduped = []
    for r in results:
        key = (r['file'], r['section'])
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    
    return deduped[:MAX_RESULTS_PER_HOP]


def extract_branch_keywords(results, original_terms):
    """Extract new keywords from search results for second hop."""
    original_lower = {t.lower() for t in original_terms}
    word_freq = defaultdict(int)
    
    for r in results:
        words = re.findall(r'\b[A-Za-z]{4,}\b', r['context'])
        for word in words:
            w = word.lower()
            if w not in STOP_WORDS and w not in original_lower:
                word_freq[w] += 1
    
    # Also grab capitalized proper nouns and TN numbers
    for r in results:
        for match in re.findall(r'\b(TN\d+|[A-Z][a-z]{3,})\b', r['context']):
            if match.lower() not in original_lower:
                word_freq[match] += 2  # boost proper nouns
    
    # Return top keywords by frequency
    sorted_kw = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    return [kw for kw, freq in sorted_kw[:5] if freq >= 2]


def main():
    if len(sys.argv) < 2:
        print("Usage: python branching-search.py \"your search query\"")
        sys.exit(1)
    
    query = sys.argv[1]
    terms = [t for t in query.split() if t.lower() not in STOP_WORDS and len(t) > 2]
    
    if not terms:
        terms = query.split()
    
    print(f"=== HOP 1: Searching for: {', '.join(terms)} ===\n")
    hop1_results = search_files(terms)
    
    if not hop1_results:
        print("No results found.")
        return
    
    for r in hop1_results:
        print(f"📍 {r['file']}:{r['line']} {r['section']}")
        print(f"   {r['text'][:120]}")
        print()
    
    # Extract branch keywords
    branch_keywords = extract_branch_keywords(hop1_results, terms)
    
    if not branch_keywords:
        print("No branch keywords extracted. Stopping at hop 1.")
        return
    
    searched_files = {r['file'] for r in hop1_results}
    
    print(f"\n=== HOP 2: Branching to: {', '.join(branch_keywords)} ===\n")
    hop2_results = search_files(branch_keywords)
    
    # Filter out results already in hop 1
    hop1_keys = {(r['file'], r['section']) for r in hop1_results}
    hop2_new = [r for r in hop2_results if (r['file'], r['section']) not in hop1_keys]
    
    if not hop2_new:
        print("No new results from branching.")
        return
    
    for r in hop2_new:
        print(f"🌿 {r['file']}:{r['line']} {r['section']}")
        print(f"   {r['text'][:120]}")
        print()
    
    print(f"\n=== SUMMARY ===")
    print(f"Hop 1: {len(hop1_results)} results from {len(set(r['file'] for r in hop1_results))} files")
    print(f"Hop 2: {len(hop2_new)} NEW results from branching on: {', '.join(branch_keywords)}")
    print(f"Total unique contexts: {len(hop1_results) + len(hop2_new)}")


if __name__ == "__main__":
    main()
