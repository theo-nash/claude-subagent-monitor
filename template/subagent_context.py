#!/usr/bin/env python3
"""
Subagent Context API
Provides easy access to the current calling subagent for other hooks.
"""

import os
import json
import time
from typing import Optional, Dict, Any, Tuple
from pathlib import Path

class SubagentContext:
    """
    Simple API for other hooks to determine the calling subagent.
    
    Usage in another hook:
        from subagent_context import SubagentContext
        
        context = SubagentContext()
        subagent = context.get_current_subagent()
        
        if subagent:
            print(f"Called by: {subagent['type']} (confidence: {subagent['confidence']})")
    """
    
    def __init__(self, data_dir: str = None):
        """Initialize with optional data directory override."""
        if data_dir is None:
            # Try global installation first
            global_dir = Path.home() / '.claude' / 'subagent-monitor' / 'data'
            if global_dir.exists():
                self.data_dir = str(global_dir)
            else:
                # Fall back to project installation
                project_dir = Path('.claude') / 'subagent-monitor' / 'data'
                if project_dir.exists():
                    self.data_dir = str(project_dir)
                else:
                    # Use environment variable if set
                    self.data_dir = os.environ.get('SUBAGENT_DATA_DIR', str(global_dir))
        else:
            self.data_dir = data_dir
        
        self.state_file = os.path.join(self.data_dir, 'active_subagents.json')
    
    def get_current_subagent(self, session_id: str = None) -> Optional[Dict[str, Any]]:
        """
        Get the currently active subagent for the session.
        
        Args:
            session_id: Optional session ID. If not provided, tries to get from environment.
        
        Returns:
            Dictionary with subagent info or None if no active subagent:
            {
                'type': 'general-purpose',
                'confidence': 1.0,
                'description': 'Task description',
                'started_at': timestamp,
                'tracking_id': 'uuid'
            }
        """
        # Try to get session_id from environment if not provided
        if session_id is None:
            session_id = os.environ.get('CLAUDE_SESSION_ID', 
                                       os.environ.get('SESSION_ID'))
        
        if not session_id:
            return None
        
        # Read active subagents
        active_subagents = self._get_active_subagents()
        
        # Find subagents for this session
        session_subagents = [
            sub for sub in active_subagents 
            if sub.get('session_id') == session_id
        ]
        
        if not session_subagents:
            return None
        
        # If only one, confidence is high
        if len(session_subagents) == 1:
            sub = session_subagents[0]
            return {
                'type': sub['subagent_type'],
                'confidence': 1.0,
                'description': sub.get('description', ''),
                'started_at': sub.get('start_time'),
                'tracking_id': sub.get('tracking_id')
            }
        
        # Multiple active - return the most recent with lower confidence
        most_recent = max(session_subagents, key=lambda x: x.get('start_time', 0))
        return {
            'type': most_recent['subagent_type'],
            'confidence': 0.7,  # Lower confidence due to multiple active
            'description': most_recent.get('description', ''),
            'started_at': most_recent.get('start_time'),
            'tracking_id': most_recent.get('tracking_id'),
            'note': f'{len(session_subagents)} subagents active'
        }
    
    def get_all_active_subagents(self, session_id: str = None) -> list:
        """
        Get all active subagents, optionally filtered by session.
        
        Returns:
            List of active subagent dictionaries.
        """
        active_subagents = self._get_active_subagents()
        
        if session_id:
            return [
                sub for sub in active_subagents 
                if sub.get('session_id') == session_id
            ]
        
        return active_subagents
    
    def is_subagent_context(self, session_id: str = None) -> bool:
        """
        Quick check if currently running in a subagent context.
        
        Returns:
            True if there's at least one active subagent, False otherwise.
        """
        return self.get_current_subagent(session_id) is not None
    
    def get_subagent_chain(self, session_id: str = None) -> list:
        """
        Get the chain of subagents (for nested Task calls).
        
        Returns:
            List of subagent types from oldest to newest.
        """
        subagents = self.get_all_active_subagents(session_id)
        
        # Sort by start time
        subagents.sort(key=lambda x: x.get('start_time', 0))
        
        return [sub['subagent_type'] for sub in subagents]
    
    def _get_active_subagents(self) -> list:
        """Read active subagents from state file."""
        if not os.path.exists(self.state_file):
            return []
        
        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)
            
            # Filter for active status
            active = []
            for tracking_id, sub in state.items():
                if sub.get('status') == 'active':
                    sub['tracking_id'] = tracking_id
                    active.append(sub)
            
            return active
        except Exception:
            return []
    
    @staticmethod
    def require_subagent(subagent_types: list = None):
        """
        Decorator to ensure a function only runs in subagent context.
        
        Args:
            subagent_types: Optional list of allowed subagent types.
        
        Usage:
            @SubagentContext.require_subagent(['code-reviewer', 'test-runner'])
            def my_hook_function():
                # This will only run if called by specified subagents
                pass
        """
        def decorator(func):
            def wrapper(*args, **kwargs):
                context = SubagentContext()
                current = context.get_current_subagent()
                
                if not current:
                    print(f"[{func.__name__}] Skipping - not in subagent context")
                    return None
                
                if subagent_types and current['type'] not in subagent_types:
                    print(f"[{func.__name__}] Skipping - wrong subagent type: {current['type']}")
                    return None
                
                # Add subagent info to kwargs for convenience
                kwargs['_subagent'] = current
                return func(*args, **kwargs)
            
            return wrapper
        return decorator


# Convenience functions for simple use cases
def get_calling_subagent(session_id: str = None) -> Optional[str]:
    """
    Simple function to get the calling subagent type.
    
    Returns:
        Subagent type string or None if not in subagent context.
    """
    context = SubagentContext()
    subagent = context.get_current_subagent(session_id)
    return subagent['type'] if subagent else None


def in_subagent_context(session_id: str = None) -> bool:
    """
    Check if currently running in a subagent context.
    
    Returns:
        True if in subagent context, False otherwise.
    """
    context = SubagentContext()
    return context.is_subagent_context(session_id)


# Example usage in a hook
if __name__ == "__main__":
    # Example: Check calling subagent in a hook
    import sys
    import json
    
    # Read hook input
    hook_data = json.loads(sys.stdin.read())
    session_id = hook_data.get('session_id')
    
    # Get calling subagent
    context = SubagentContext()
    subagent = context.get_current_subagent(session_id)
    
    if subagent:
        print(f"Hook called by subagent: {subagent['type']}")
        print(f"Confidence: {subagent['confidence']}")
        print(f"Description: {subagent['description']}")
        
        # Example: Different behavior based on subagent
        if subagent['type'] == 'code-reviewer':
            print("Applying stricter validation rules...")
        elif subagent['type'] == 'test-runner':
            print("Enabling test mode features...")
    else:
        print("Hook called directly (not by subagent)")