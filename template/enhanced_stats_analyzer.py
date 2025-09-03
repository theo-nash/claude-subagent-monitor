#!/usr/bin/env python3
"""
Enhanced statistics analyzer for subagent conversations.
Focuses on essential metrics: runtime, conversation turns, and file operations.
"""

import json
import os
from typing import Dict, Any, List, Set, Tuple
from collections import defaultdict
from datetime import datetime

class EnhancedStatsAnalyzer:
    """Analyzes subagent conversations for enhanced statistics."""
    
    def __init__(self):
        self.file_operations = {
            'created': set(),
            'modified': set(),
            'read': set(),
            'deleted': set()
        }
        self.existing_files = set()  # Track files that existed before
    
    def analyze_conversation(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze a subagent conversation for enhanced statistics.
        
        Returns:
            Dictionary containing:
            - total_runtime: Total conversation duration in seconds
            - total_turns: Number of conversation turns
            - files_created: Number of new files created
            - files_modified: Number of existing files modified
            - files_read: Number of files read
            - files_deleted: Number of files deleted
            - file_paths: List of all file paths touched
            - documentation_updated: Whether any .md files were modified
        """
        if not messages:
            return self._empty_stats()
        
        # Calculate runtime
        total_runtime = self._calculate_runtime(messages)
        
        # Count conversation turns (user/assistant pairs)
        total_turns = self._count_turns(messages)
        
        # Analyze file operations
        file_stats = self._analyze_file_operations(messages)
        
        return {
            'total_runtime': total_runtime,
            'total_turns': total_turns,
            'files_created': file_stats['created'],
            'files_modified': file_stats['modified'],
            'files_read': file_stats['read'],
            'files_deleted': file_stats['deleted'],
            'file_paths': file_stats['all_paths'],
            'documentation_updated': file_stats['docs_updated']
        }
    
    def _empty_stats(self) -> Dict[str, Any]:
        """Return empty statistics structure."""
        return {
            'total_runtime': 0,
            'total_turns': 0,
            'files_created': 0,
            'files_modified': 0,
            'files_read': 0,
            'files_deleted': 0,
            'file_paths': [],
            'documentation_updated': False
        }
    
    def _calculate_runtime(self, messages: List[Dict[str, Any]]) -> int:
        """Calculate total runtime in seconds."""
        if not messages:
            return 0
        
        # Get first and last timestamps
        timestamps = []
        for msg in messages:
            if 'timestamp' in msg:
                # Handle both Unix timestamps and ISO strings
                ts = msg['timestamp']
                if isinstance(ts, str):
                    # Parse ISO format
                    try:
                        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                        timestamps.append(dt.timestamp())
                    except:
                        continue
                else:
                    timestamps.append(ts)
        
        if len(timestamps) < 2:
            return 0
        
        return int(max(timestamps) - min(timestamps))
    
    def _count_turns(self, messages: List[Dict[str, Any]]) -> int:
        """Count conversation turns (back-and-forth exchanges)."""
        turns = 0
        last_role = None
        
        for msg in messages:
            role = msg.get('role', msg.get('type'))
            
            # Count a turn when we switch from assistant to user
            if last_role == 'assistant' and role == 'user':
                turns += 1
            
            last_role = role
        
        # Final turn if conversation ended with assistant
        if last_role == 'assistant':
            turns += 1
        
        return turns
    
    def _analyze_file_operations(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze all file operations in the conversation."""
        files_created = set()
        files_modified = set()
        files_read = set()
        files_deleted = set()
        all_paths = set()
        
        # First pass: identify which files existed (were read or edited)
        for msg in messages:
            # Handle both direct tool_use and nested in message.content
            tool_uses = []
            
            # Direct tool_use (sidechain format)
            if msg.get('type') == 'tool_use':
                tool_uses.append(msg)
            
            # Nested in message content (main chain format)
            if msg.get('message', {}).get('content'):
                content = msg['message']['content']
                # Content can be string or list
                if isinstance(content, list):
                    for content_item in content:
                        if isinstance(content_item, dict) and content_item.get('type') == 'tool_use':
                            tool_uses.append(content_item)
            
            for tool_use in tool_uses:
                tool_name = tool_use.get('name', '')
                params = tool_use.get('input', {})
                
                if tool_name == 'Read' and 'file_path' in params:
                    self.existing_files.add(params['file_path'])
                elif tool_name == 'Edit' and 'file_path' in params:
                    self.existing_files.add(params['file_path'])
        
        # Second pass: categorize operations
        for msg in messages:
            # Handle both direct tool_use and nested in message.content
            tool_uses = []
            
            # Direct tool_use (sidechain format)
            if msg.get('type') == 'tool_use':
                tool_uses.append(msg)
            
            # Nested in message content (main chain format)
            if msg.get('message', {}).get('content'):
                content = msg['message']['content']
                # Content can be string or list
                if isinstance(content, list):
                    for content_item in content:
                        if isinstance(content_item, dict) and content_item.get('type') == 'tool_use':
                            tool_uses.append(content_item)
            
            for tool_use in tool_uses:
                tool_name = tool_use.get('name', '')
                params = tool_use.get('input', {})
                file_path = params.get('file_path', '')
                
                if not file_path:
                    continue
                
                all_paths.add(file_path)
                
                if tool_name == 'Write':
                    if file_path in self.existing_files or file_path in files_modified:
                        files_modified.add(file_path)
                    else:
                        files_created.add(file_path)
                        # After creation, it exists
                        self.existing_files.add(file_path)
                
                elif tool_name == 'Edit' or tool_name == 'MultiEdit':
                    files_modified.add(file_path)
                
                elif tool_name == 'Read':
                    files_read.add(file_path)
                
                elif tool_name == 'Bash':
                    # Check for rm commands
                    command = params.get('command', '')
                    if 'rm ' in command or 'unlink ' in command:
                        # Simple heuristic - could be improved
                        # Try to extract filename from rm command
                        parts = command.split()
                        for i, part in enumerate(parts):
                            if part in ['rm', 'unlink'] and i + 1 < len(parts):
                                potential_file = parts[i + 1].strip('-rf')
                                if not potential_file.startswith('-'):
                                    files_deleted.add(potential_file)
                                    all_paths.add(potential_file)
        
        # Check for documentation updates
        docs_updated = any(path.endswith('.md') for path in (files_created | files_modified))
        
        return {
            'created': len(files_created),
            'modified': len(files_modified),
            'read': len(files_read),
            'deleted': len(files_deleted),
            'all_paths': sorted(list(all_paths)),
            'docs_updated': docs_updated,
            # Include the actual sets for detailed tracking if needed
            '_created_files': list(files_created),
            '_modified_files': list(files_modified),
            '_read_files': list(files_read),
            '_deleted_files': list(files_deleted)
        }
    
    def format_summary(self, stats: Dict[str, Any]) -> str:
        """Format statistics as a human-readable summary."""
        lines = [
            "📊 Subagent Statistics Summary",
            "=" * 40,
            f"⏱️  Runtime: {stats['total_runtime']}s",
            f"💬 Turns: {stats['total_turns']}",
            "",
            "📁 File Operations:",
            f"  • Created: {stats['files_created']} files",
            f"  • Modified: {stats['files_modified']} files",
            f"  • Read: {stats['files_read']} files",
            f"  • Deleted: {stats['files_deleted']} files",
            f"  • Documentation: {'✅ Updated' if stats['documentation_updated'] else '❌ Not updated'}",
        ]
        
        if stats['file_paths']:
            lines.append("")
            lines.append(f"📝 Files touched ({len(stats['file_paths'])} total):")
            for path in stats['file_paths'][:10]:  # Show first 10
                lines.append(f"  - {path}")
            if len(stats['file_paths']) > 10:
                lines.append(f"  ... and {len(stats['file_paths']) - 10} more")
        
        return '\n'.join(lines)


def analyze_subagent_conversation(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Convenience function to analyze a subagent conversation."""
    analyzer = EnhancedStatsAnalyzer()
    return analyzer.analyze_conversation(messages)


# Example usage
if __name__ == "__main__":
    # Example messages structure
    example_messages = [
        {
            'timestamp': '2024-01-01T10:00:00Z',
            'role': 'user',
            'content': 'Create a new module'
        },
        {
            'timestamp': '2024-01-01T10:00:05Z',
            'role': 'assistant',
            'type': 'tool_use',
            'name': 'Write',
            'input': {'file_path': 'new_module.py'}
        },
        {
            'timestamp': '2024-01-01T10:00:10Z',
            'role': 'assistant',
            'type': 'tool_use',
            'name': 'Read',
            'input': {'file_path': 'config.json'}
        },
        {
            'timestamp': '2024-01-01T10:00:15Z',
            'role': 'assistant',
            'type': 'tool_use',
            'name': 'Edit',
            'input': {'file_path': 'config.json'}
        },
        {
            'timestamp': '2024-01-01T10:00:20Z',
            'role': 'assistant',
            'type': 'tool_use',
            'name': 'Write',
            'input': {'file_path': 'README.md'}
        },
        {
            'timestamp': '2024-01-01T10:00:30Z',
            'role': 'user',
            'content': 'Great, now test it'
        },
        {
            'timestamp': '2024-01-01T10:00:35Z',
            'role': 'assistant',
            'content': 'Testing the module...'
        }
    ]
    
    analyzer = EnhancedStatsAnalyzer()
    stats = analyzer.analyze_conversation(example_messages)
    
    print(analyzer.format_summary(stats))
    print("\n📊 Raw statistics:")
    print(json.dumps(stats, indent=2))