#!/usr/bin/env python3
"""
Enhanced transcript parser for Claude Code subagent tracking.
Uses UUID chain reconstruction to accurately extract subagent conversations.
"""

import json
import os
from typing import Dict, Any, List, Tuple, Optional
from collections import defaultdict, Counter
from sidechain_reconstructor import SidechainReconstructor

class TranscriptParser:
    def __init__(self, transcript_path: str):
        self.transcript_path = transcript_path
        self.reconstructor = SidechainReconstructor(transcript_path)
        self.subagent_chains = []
    
    def load_and_reconstruct(self) -> bool:
        """Load transcript and reconstruct all subagent chains."""
        if not self.reconstructor.load_transcript():
            return False
        
        self.subagent_chains = self.reconstructor.reconstruct_all_subagent_chains()
        return len(self.subagent_chains) > 0
    
    def get_subagent_conversation(self, subagent_type: str, occurrence: int = 0) -> Optional[List[Dict]]:
        """
        Get a specific subagent conversation.
        
        Args:
            subagent_type: The type of subagent (e.g., 'sdk-protocol-specialist')
            occurrence: Which occurrence to get (0 = first, 1 = second, etc.)
        
        Returns:
            List of messages in the conversation chain, or None if not found
        """
        matching_chains = [
            chain for chain in self.subagent_chains 
            if chain['subagent_type'] == subagent_type
        ]
        
        if occurrence < len(matching_chains):
            return matching_chains[occurrence]['messages']
        
        return None
    
    def get_latest_subagent_conversation(self, subagent_type: str) -> Optional[List[Dict]]:
        """
        Get the most recent conversation for a specific subagent type.
        
        Args:
            subagent_type: The type of subagent (e.g., 'sdk-protocol-specialist')
        
        Returns:
            List of messages in the most recent conversation chain, or None if not found
        """
        matching_chains = [
            chain for chain in self.subagent_chains 
            if chain['subagent_type'] == subagent_type
        ]
        
        if not matching_chains:
            return None
        
        # Chains are already in order from reconstruction (based on Task line numbers)
        # Return the last one
        return matching_chains[-1]['messages']
    
    def get_subagent_occurrence_count(self, subagent_type: str) -> int:
        """
        Get the number of times a specific subagent type was invoked.
        
        Args:
            subagent_type: The type of subagent
        
        Returns:
            Number of invocations
        """
        return len([
            chain for chain in self.subagent_chains 
            if chain['subagent_type'] == subagent_type
        ])
    
    def get_latest_subagent_info(self, subagent_type: str) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive info about the most recent invocation of a subagent type.
        
        Args:
            subagent_type: The type of subagent
        
        Returns:
            Dict with chain info, statistics, and metadata, or None if not found
        """
        matching_chains = [
            chain for chain in self.subagent_chains 
            if chain['subagent_type'] == subagent_type
        ]
        
        if not matching_chains:
            return None
        
        # Get the latest chain
        latest_chain = matching_chains[-1]
        messages = latest_chain['messages']
        
        # Build comprehensive info
        info = {
            'subagent_type': subagent_type,
            'occurrence_index': len(matching_chains) - 1,  # Index of this occurrence
            'total_occurrences': len(matching_chains),
            'description': latest_chain['description'],
            'task_line': latest_chain['task_line'],
            'chain_length': latest_chain['chain_length'],
            'messages': messages,
            'tool_usage': self.analyze_tool_usage(messages),
            'message_stats': self.analyze_message_statistics(messages),
            'estimated_tokens': self.estimate_token_count(messages),
            'task_timestamp': latest_chain.get('task_timestamp', 0),
            'root_uuid': latest_chain.get('root_uuid', '')
        }
        
        # Add computed stats
        info['total_tools_used'] = sum(info['tool_usage'].values())
        info['unique_tools_used'] = len(info['tool_usage'])
        
        return info
    
    def analyze_tool_usage(self, messages: List[Dict[str, Any]]) -> Dict[str, int]:
        """Analyze tool usage from subagent messages."""
        tool_usage = Counter()
        
        for entry in messages:
            msg = entry.get('message', {})
            if msg.get('role') == 'assistant':
                content = msg.get('content', [])
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get('type') == 'tool_use':
                            tool_name = item.get('name')
                            if tool_name:
                                tool_usage[tool_name] += 1
        
        return dict(tool_usage)
    
    def analyze_message_statistics(self, messages: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
        """Analyze message statistics by type."""
        stats = defaultdict(lambda: {'count': 0, 'total_chars': 0})
        
        for entry in messages:
            msg = entry.get('message', {})
            role = msg.get('role', 'unknown')
            
            # Calculate content length
            content = msg.get('content', '')
            if isinstance(content, list):
                content_str = json.dumps(content)
            else:
                content_str = str(content)
            
            stats[role]['count'] += 1
            stats[role]['total_chars'] += len(content_str)
        
        # Calculate averages
        for role in stats:
            count = stats[role]['count']
            if count > 0:
                stats[role]['avg_chars'] = stats[role]['total_chars'] / count
            else:
                stats[role]['avg_chars'] = 0
        
        return dict(stats)
    
    def estimate_token_count(self, messages: List[Dict[str, Any]]) -> int:
        """Estimate token count for messages (rough approximation)."""
        total_chars = 0
        
        for entry in messages:
            msg = entry.get('message', {})
            content = msg.get('content', '')
            
            if isinstance(content, list):
                content_str = json.dumps(content)
            else:
                content_str = str(content)
            
            total_chars += len(content_str)
        
        # Rough approximation: 1 token ≈ 4 characters for English text
        return total_chars // 4
    
    def get_subagent_summary(self, subagent_type: str) -> Dict[str, Any]:
        """Get comprehensive summary for all invocations of a specific subagent type."""
        matching_chains = [
            chain for chain in self.subagent_chains 
            if chain['subagent_type'] == subagent_type
        ]
        
        if not matching_chains:
            return None
        
        summary = {
            'subagent_type': subagent_type,
            'total_invocations': len(matching_chains),
            'invocations': []
        }
        
        for i, chain in enumerate(matching_chains):
            messages = chain['messages']
            
            invocation_info = {
                'occurrence': i,
                'description': chain['description'],
                'task_line': chain['task_line'],
                'chain_length': chain['chain_length'],
                'tool_usage': self.analyze_tool_usage(messages),
                'message_stats': self.analyze_message_statistics(messages),
                'estimated_tokens': self.estimate_token_count(messages)
            }
            
            # Calculate totals
            invocation_info['total_tools_used'] = sum(invocation_info['tool_usage'].values())
            invocation_info['unique_tools_used'] = len(invocation_info['tool_usage'])
            
            summary['invocations'].append(invocation_info)
        
        # Calculate aggregates
        summary['total_messages'] = sum(inv['chain_length'] for inv in summary['invocations'])
        summary['total_tokens_estimated'] = sum(inv['estimated_tokens'] for inv in summary['invocations'])
        summary['avg_messages_per_invocation'] = summary['total_messages'] / len(matching_chains)
        
        # Aggregate tool usage
        all_tools = Counter()
        for inv in summary['invocations']:
            for tool, count in inv['tool_usage'].items():
                all_tools[tool] += count
        summary['aggregate_tool_usage'] = dict(all_tools)
        
        return summary
    
    def get_all_subagents_summary(self) -> List[Dict[str, Any]]:
        """Get summary for all unique subagent types."""
        subagent_types = set(chain['subagent_type'] for chain in self.subagent_chains)
        summaries = []
        
        for subagent_type in subagent_types:
            summary = self.get_subagent_summary(subagent_type)
            if summary:
                summaries.append(summary)
        
        return summaries


def parse_transcript_for_subagent_v2(transcript_path: str, subagent_type: str, 
                                     occurrence: int = 0) -> Tuple[Dict[str, int], Dict[str, Dict[str, int]], int]:
    """
    Parse transcript and return tool usage, message stats, and token estimate for a specific subagent.
    
    Args:
        transcript_path: Path to the JSONL transcript file
        subagent_type: Type of subagent to analyze
        occurrence: Which occurrence of this subagent type (0 = first, 1 = second, etc.)
    
    Returns:
        Tuple of (tool_usage, message_stats, token_estimate)
    """
    parser = TranscriptParser(transcript_path)
    
    if not parser.load_and_reconstruct():
        return {}, {}, 0
    
    messages = parser.get_subagent_conversation(subagent_type, occurrence)
    
    if not messages:
        return {}, {}, 0
    
    tool_usage = parser.analyze_tool_usage(messages)
    message_stats = parser.analyze_message_statistics(messages)
    token_estimate = parser.estimate_token_count(messages)
    
    return tool_usage, message_stats, token_estimate


def parse_latest_subagent_conversation(transcript_path: str, subagent_type: str) -> Tuple[Dict[str, int], Dict[str, Dict[str, int]], int]:
    """
    Parse transcript and return stats for the LATEST occurrence of a specific subagent.
    
    Args:
        transcript_path: Path to the JSONL transcript file
        subagent_type: Type of subagent to analyze
    
    Returns:
        Tuple of (tool_usage, message_stats, token_estimate)
    """
    parser = TranscriptParser(transcript_path)
    
    if not parser.load_and_reconstruct():
        return {}, {}, 0
    
    messages = parser.get_latest_subagent_conversation(subagent_type)
    
    if not messages:
        return {}, {}, 0
    
    tool_usage = parser.analyze_tool_usage(messages)
    message_stats = parser.analyze_message_statistics(messages)
    token_estimate = parser.estimate_token_count(messages)
    
    return tool_usage, message_stats, token_estimate


def test_v2_parser():
    """Test the enhanced parser with chain reconstruction."""
    # Example usage - replace with your actual transcript path
    transcript_path = '~/.claude/projects/YOUR_PROJECT/YOUR_SESSION_ID.jsonl'
    
    print("=== Testing Enhanced Transcript Parser V2 ===\n")
    
    parser = TranscriptParser(transcript_path)
    
    print("1. Loading and reconstructing chains...")
    if parser.load_and_reconstruct():
        print(f"   ✓ Reconstructed {len(parser.subagent_chains)} subagent chains")
    else:
        print("   ✗ Failed to reconstruct chains")
        return
    
    print("\n2. Analyzing all subagents:")
    summaries = parser.get_all_subagents_summary()
    
    for summary in summaries:
        print(f"\n   {summary['subagent_type']}:")
        print(f"   - Total invocations: {summary['total_invocations']}")
        print(f"   - Total messages: {summary['total_messages']}")
        print(f"   - Average messages per invocation: {summary['avg_messages_per_invocation']:.1f}")
        print(f"   - Total estimated tokens: {summary['total_tokens_estimated']:,}")
        
        print(f"\n   Top tools used across all invocations:")
        top_tools = sorted(summary['aggregate_tool_usage'].items(), key=lambda x: x[1], reverse=True)[:5]
        for tool, count in top_tools:
            print(f"     - {tool}: {count} uses")
        
        print(f"\n   Individual invocations:")
        for inv in summary['invocations']:
            print(f"     {inv['occurrence']+1}. {inv['description'][:40]}...")
            print(f"        Messages: {inv['chain_length']}, Tools: {inv['total_tools_used']}, Tokens: {inv['estimated_tokens']:,}")
    
    print("\n3. Testing specific subagent extraction:")
    # Test getting the first sdk-protocol-specialist conversation
    tool_usage, msg_stats, tokens = parse_transcript_for_subagent_v2(
        transcript_path, 'sdk-protocol-specialist', occurrence=0
    )
    
    print(f"   First 'sdk-protocol-specialist' invocation:")
    print(f"   - Tool usage: {len(tool_usage)} different tools, {sum(tool_usage.values())} total uses")
    print(f"   - Message breakdown:")
    for role, stats in msg_stats.items():
        print(f"     - {role}: {stats['count']} messages")
    print(f"   - Estimated tokens: {tokens:,}")
    
    print("\n=== Test Complete ===")
    print("\nKey improvements in V2:")
    print("✓ Accurate chain reconstruction using UUID linking")
    print("✓ Proper handling of concurrent subagents")
    print("✓ Exact prompt matching for chain identification")
    print("✓ Support for multiple invocations of same subagent type")
    print("✓ Complete conversation extraction including all sidechain messages")


if __name__ == "__main__":
    test_v2_parser()