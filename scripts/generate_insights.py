#!/usr/bin/env python3
"""
Generate insights from video performance data.
Shows which topics, categories, and hook styles are performing best.

Usage:
    python scripts/generate_insights.py [--top N]

Examples:
    python scripts/generate_insights.py                # Show all stats
    python scripts/generate_insights.py --top 3        # Show top 3 in each category
"""

import sys
import argparse
import json
from datetime import datetime
from pathlib import Path

# Add parent directory to path so we can import agents
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.analytics_agent import (
    load_performance_history,
    get_performance_stats
)


def print_separator(title=""):
    """Print a formatted separator line."""
    if title:
        print(f"\n{'='*70}")
        print(f" {title}")
        print(f"{'='*70}\n")
    else:
        print(f"\n{'-'*70}\n")


def print_performance_table(
    data,
    name,
    top_n=None
):
    """
    Print a formatted performance table for a category.
    
    Args:
        data: dict of {item: {count, views, likes, comments}}
        name: category name (e.g., "Topics")
        top_n: if set, only show top N items by views
    """
    
    if not data:
        print(f"No data for {name}")
        return
    
    # Sort by views descending
    sorted_items = sorted(
        data.items(),
        key=lambda x: x[1].get("views", 0),
        reverse=True
    )
    
    if top_n:
        sorted_items = sorted_items[:top_n]
    
    print(f"\n{name}:")
    print(f"{'Item':<40} {'Count':<8} {'Avg Views':<12} {'Avg Likes':<12} {'Avg Comments':<12}")
    print(f"{'-'*40} {'-'*8} {'-'*12} {'-'*12} {'-'*12}")
    
    for item, metrics in sorted_items:
        
        count = metrics.get("count", 0)
        
        if count == 0:
            continue
        
        avg_views = metrics.get("views", 0) / count
        avg_likes = metrics.get("likes", 0) / count
        avg_comments = metrics.get("comments", 0) / count
        
        # Truncate long item names
        display_name = (
            item[:37] + "..."
            if len(item) > 40
            else item
        )
        
        print(
            f"{display_name:<40} "
            f"{count:<8} "
            f"{avg_views:<12.0f} "
            f"{avg_likes:<12.1f} "
            f"{avg_comments:<12.1f}"
        )


def print_recommendations(stats):
    """Generate actionable recommendations based on stats."""
    
    print_separator("RECOMMENDATIONS")
    
    if not stats or not stats.get("by_topic"):
        print("Not enough data for recommendations yet.")
        print("Keep uploading videos and check back in 1-2 weeks.")
        return
    
    # Find best-performing topic
    best_topic = max(
        stats["by_topic"].items(),
        key=lambda x: x[1].get("views", 0) / max(x[1].get("count", 1), 1),
        default=(None, {})
    )
    
    if best_topic[0]:
        avg_views = best_topic[1]["views"] / best_topic[1]["count"]
        print(
            f"✓ BEST PERFORMING TOPIC: '{best_topic[0]}'\n"
            f"  Average views: {avg_views:.0f}\n"
            f"  Videos created: {best_topic[1]['count']}\n"
            f"  → Generate more videos in this topic"
        )
    
    # Find best hook style
    best_hook = max(
        stats["by_hook_style"].items(),
        key=lambda x: x[1].get("likes", 0) / max(x[1].get("count", 1), 1),
        default=(None, {})
    )
    
    if best_hook[0]:
        avg_likes = best_hook[1]["likes"] / best_hook[1]["count"]
        print(
            f"\n✓ BEST HOOK STYLE: '{best_hook[0]}'\n"
            f"  Average likes: {avg_likes:.1f}\n"
            f"  Videos created: {best_hook[1]['count']}\n"
            f"  → Bias hook selection toward this style"
        )
    
    # Find best category
    best_category = max(
        stats["by_category"].items(),
        key=lambda x: x[1].get("comments", 0) / max(x[1].get("count", 1), 1),
        default=(None, {})
    )
    
    if best_category[0]:
        avg_comments = best_category[1]["comments"] / best_category[1]["count"]
        print(
            f"\n✓ BEST ENGAGEMENT CATEGORY: '{best_category[0]}'\n"
            f"  Average comments: {avg_comments:.1f}\n"
            f"  Videos created: {best_category[1]['count']}\n"
            f"  → Prioritize this category for comment-farming CTAs"
        )
    
    # Overall insights
    overall = stats.get("overall", {})
    
    if overall.get("avg_duration"):
        print(
            f"\n📊 OVERALL METRICS:\n"
            f"  Total videos: {overall.get('total_videos', 0)}\n"
            f"  Average views per video: {overall.get('avg_views', 0):.0f}\n"
            f"  Average completion rate: "
            f"{overall.get('avg_duration', 0):.1f} seconds\n"
        )


def print_underperformers(stats):
    """Identify underperforming content."""
    
    print_separator("UNDERPERFORMERS")
    
    if not stats or not stats.get("by_topic"):
        return
    
    # Sort by views (ascending) to find worst performers
    worst_topics = sorted(
        stats["by_topic"].items(),
        key=lambda x: x[1].get("views", 0) / max(x[1].get("count", 1), 1)
    )[:3]
    
    if worst_topics and worst_topics[0][0]:
        print("Topics with lowest views:")
        
        for topic, metrics in worst_topics:
            if metrics.get("count", 0) > 0:
                avg_views = metrics["views"] / metrics["count"]
                print(f"  • {topic}: {avg_views:.0f} avg views")
        
        print(
            "\nOptions:\n"
            "  1. These topics may not resonate with your audience\n"
            "  2. Try different hook styles for these topics\n"
            "  3. Consider pausing these topics for 2 weeks"
        )


def main():
    
    parser = argparse.ArgumentParser(
        description="Generate insights from video performance data"
    )
    
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="Show only top N items in each category"
    )
    
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of formatted text"
    )
    
    args = parser.parse_args()
    
    # Load performance history
    history = load_performance_history()
    
    if not history:
        print("No performance data found yet.")
        print("Upload some videos first, wait 24-48 hours for YouTube Analytics to populate,")
        print("then run this script again.")
        return 1
    
    # Get stats
    stats = get_performance_stats()
    
    if not stats:
        print("Could not calculate stats from history.")
        return 1
    
    if args.json:
        
        # Output raw JSON
        print(json.dumps(stats, indent=2))
    
    else:
        
        # Formatted output
        print_separator("VIDEO PERFORMANCE ANALYSIS")
        
        print(
            f"Analysis generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Total videos tracked: {len(history)}"
        )
        
        # Show performance by category
        print_performance_table(
            stats.get("by_topic", {}),
            "TOP PERFORMING TOPICS",
            top_n=args.top
        )
        
        print_performance_table(
            stats.get("by_category", {}),
            "TOP PERFORMING CATEGORIES",
            top_n=args.top
        )
        
        print_performance_table(
            stats.get("by_hook_style", {}),
            "TOP PERFORMING HOOK STYLES",
            top_n=args.top
        )
        
        # Show recommendations
        print_recommendations(stats)
        
        # Show underperformers
        print_underperformers(stats)
        
        print_separator()
        
        print(
            "Next steps:\n"
            "  1. Bias topic selection toward top performers\n"
            "  2. Reduce or pause underperforming topics\n"
            "  3. Weight hook styles by performance\n"
            "  4. Check back weekly to track trends\n"
        )
    
    return 0


if __name__ == "__main__":
    sys.exit(main())