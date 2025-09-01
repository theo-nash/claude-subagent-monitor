#!/usr/bin/env python3
"""
Enhanced transcript parser for Claude Code subagent tracking.
Consolidates all parsing improvements including UUID chain reconstruction.
"""

import json
import os
from typing import Dict, Any, List, Tuple, Optional
from collections import defaultdict, Counter

# Import the chain reconstructor (will be in same hooks directory)
try:
    from sidechain_reconstructor import SidechainReconstructor
except ImportError:
    # Fallback if not available
    SidechainReconstructor = None

class TranscriptParser:
    """
    Enhanced transcript parser with UUID chain reconstruction support.
    """
    
    def __init__(self, transcript_path: str):
        self.transcript_path = transcript_path
        self.reconstructor = None
        self.subagent_chains = []
        
        # Try to use chain reconstruction if available
        if SidechainReconstructor:
            self.reconstructor = SidechainReconstructor(transcript_path)
    
    def load_and_reconstruct(self) -> bool:
        """Load transcript and reconstruct all subagent chains."""
        if not self.reconstructor:
            return False
            
        if not self.reconstructor.load_transcript():
            return False
        
        self.subagent_chains = self.reconstructor.reconstruct_all_subagent_chains()
        return len(self.subagent_chains) > 0
    
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
        
        # Return the last one (most recent)
        return matching_chains[-1]['messages']
    
    def get_subagent_conversation(self, subagent_type: str, occurrence: int = 0) -> Optional[List[Dict]]:
        """
        Get a specific subagent conversation by occurrence index.
        
        Args:
            subagent_type: The type of subagent
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
    
    def get_latest_subagent_info(self, subagent_type: str) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive info about the most recent invocation of a subagent type.
        
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
            'occurrence_index': len(matching_chains) - 1,
            'total_occurrences': len(matching_chains),
            'description': latest_chain.get('description', ''),
            'task_line': latest_chain.get('task_line', 0),
            'chain_length': latest_chain.get('chain_length', len(messages)),
            'messages': messages,
            'tool_usage': self.analyze_tool_usage(messages),
            'message_stats': self.analyze_message_statistics(messages),
            'estimated_tokens': self.estimate_token_count(messages)
        }
        
        # Add computed stats
        info['total_tools_used'] = sum(info['tool_usage'].values())
        info['unique_tools_used'] = len(info['tool_usage'])
        
        return info


def parse_latest_subagent_conversation(transcript_path: str, subagent_type: str) -> Tuple[Dict[str, int], Dict[str, Dict[str, int]], int]:
    """
    Parse transcript and return stats for the LATEST occurrence of a specific subagent.
    
    This is the main function used by hooks.
    
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


def parse_transcript_for_subagent(transcript_path: str, subagent_type: str, 
                                  occurrence: int = 0) -> Tuple[Dict[str, int], Dict[str, Dict[str, int]], int]:
    """
    Parse transcript and return stats for a specific occurrence of a subagent.
    
    Args:
        transcript_path: Path to the JSONL transcript file
        subagent_type: Type of subagent to analyze
        occurrence: Which occurrence of this subagent type (0 = first, -1 = latest)
    
    Returns:
        Tuple of (tool_usage, message_stats, token_estimate)
    """
    if occurrence == -1:
        # Use the latest conversation
        return parse_latest_subagent_conversation(transcript_path, subagent_type)
    
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