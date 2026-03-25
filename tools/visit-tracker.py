#!/usr/bin/env python3
"""
Spiral Depth — Visit tracker for topic-based retrieval depth.

Tracks how many times a topic has been retrieved and suggests
what depth of context to serve based on visit frequency.

Usage:
    python visit-tracker.py log "birefringence"    # Log a visit
    python visit-tracker.py check "birefringence"  # Check depth level
    python visit-tracker.py stats                   # Show all tracked topics
"""

import json
import os
import sys
from datetime import datetime

VISIT_LOG = os.environ.get("VISIT_LOG", "memory/visit-log.json")

DEPTH_THRESHOLDS = {
    "surface": (1, 2),       # visits 1-2: basic context
    "shelf": (3, 5),         # visits 3-5: theme files, cross-references
    "thermocline": (6, 10),  # visits 6-10: recipes, deep research
    "abyss": (11, float('inf')),  # visits 11+: crystals, core connections
}


def load_log():
    if os.path.isfile(VISIT_LOG):
        with open(VISIT_LOG, 'r') as f:
            return json.load(f)
    return {}


def save_log(data):
    os.makedirs(os.path.dirname(VISIT_LOG) or '.', exist_ok=True)
    with open(VISIT_LOG, 'w') as f:
        json.dump(data, f, indent=2)


def get_depth(visits):
    for depth, (low, high) in DEPTH_THRESHOLDS.items():
        if low <= visits <= high:
            return depth
    return "abyss"


def log_visit(topic):
    data = load_log()
    topic_lower = topic.lower()
    
    if topic_lower not in data:
        data[topic_lower] = {
            "visits": 0,
            "first_visited": datetime.now().isoformat(),
            "last_visited": None,
            "history": [],
        }
    
    data[topic_lower]["visits"] += 1
    data[topic_lower]["last_visited"] = datetime.now().isoformat()
    data[topic_lower]["history"].append(datetime.now().isoformat())
    
    # Keep only last 20 visit timestamps
    data[topic_lower]["history"] = data[topic_lower]["history"][-20:]
    
    save_log(data)
    
    visits = data[topic_lower]["visits"]
    depth = get_depth(visits)
    
    print(f"📊 {topic}: visit #{visits} → serve {depth} context")
    
    # Suggest what to retrieve based on depth
    suggestions = {
        "surface": "Daily notes, basic definitions, recent mentions",
        "shelf": "Theme files, cross-references, related specimens/topics",
        "thermocline": "Recipes, deep research threads, crystals, full paragenesis",
        "abyss": "Core connections, archetypes, cross-domain links, everything",
    }
    print(f"   Suggestion: {suggestions[depth]}")


def check_topic(topic):
    data = load_log()
    topic_lower = topic.lower()
    
    if topic_lower not in data:
        print(f"❓ {topic}: never visited → serve surface context (basics)")
        return
    
    entry = data[topic_lower]
    depth = get_depth(entry["visits"])
    print(f"📊 {topic}: {entry['visits']} visits, last {entry['last_visited'][:10]} → {depth}")


def show_stats():
    data = load_log()
    if not data:
        print("No topics tracked yet.")
        return
    
    # Sort by visits descending
    sorted_topics = sorted(data.items(), key=lambda x: x[1]["visits"], reverse=True)
    
    print(f"{'Topic':<30} {'Visits':>6} {'Depth':<14} {'Last Visited':<12}")
    print("-" * 65)
    
    for topic, entry in sorted_topics:
        depth = get_depth(entry["visits"])
        last = entry["last_visited"][:10] if entry["last_visited"] else "never"
        print(f"{topic:<30} {entry['visits']:>6} {depth:<14} {last:<12}")
    
    print(f"\nTotal topics tracked: {len(data)}")
    
    # Depth distribution
    depths = {}
    for _, entry in data.items():
        d = get_depth(entry["visits"])
        depths[d] = depths.get(d, 0) + 1
    
    print(f"Depth distribution: {', '.join(f'{d}={c}' for d, c in sorted(depths.items()))}")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python visit-tracker.py log \"topic\"     # Log a visit")
        print("  python visit-tracker.py check \"topic\"   # Check depth")
        print("  python visit-tracker.py stats            # Show all")
        sys.exit(1)
    
    action = sys.argv[1]
    
    if action == "log" and len(sys.argv) >= 3:
        log_visit(sys.argv[2])
    elif action == "check" and len(sys.argv) >= 3:
        check_topic(sys.argv[2])
    elif action == "stats":
        show_stats()
    else:
        print(f"Unknown action: {action}")


if __name__ == "__main__":
    main()
