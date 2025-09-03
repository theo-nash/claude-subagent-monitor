#!/usr/bin/env python3
"""
MCP Context Helper - Enables MCPs to identify their calling session and agent.

This module provides a simple API for MCP servers to retrieve context about
their caller without any protocol modifications.

Usage in MCP server:
    from mcp_context import get_caller_context, with_context
    
    # Simple usage
    context = get_caller_context("my_tool", params)
    if context:
        print(f"Called by session {context['session_id']}")
        print(f"Agent: {context['agent_type']}")
    
    # Decorator usage
    @with_context
    async def my_tool(params, context=None):
        if context:
            session_id = context['session_id']
            # Use session/agent info for logging, rate limiting, etc.
"""

import os
import sys
import json
import functools
from typing import Dict, Any, Optional, Callable
from pathlib import Path

# Add correlation service to path
def _setup_path():
    """Setup path to find correlation service."""
    # Try multiple possible locations
    possible_paths = [
        # Installed location
        os.path.expanduser('~/.claude/subagent-monitor/lib'),
        os.path.expanduser('./.claude/subagent-monitor/lib'),
        # Development location
        os.path.dirname(os.path.abspath(__file__)),
        # Template location
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'template')
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            if path not in sys.path:
                sys.path.insert(0, path)
            break

_setup_path()

try:
    from mcp_correlation_service import retrieve_mcp_context
except ImportError:
    # Fallback if correlation service not available
    def retrieve_mcp_context(tool_name: str, params: Any) -> Optional[Dict[str, Any]]:
        return None


class MCPContext:
    """Helper class for MCP context retrieval."""
    
    def __init__(self):
        self._cache = {}
        self._debug = os.environ.get('MCP_CONTEXT_DEBUG', '').lower() == 'true'
    
    def get_context(self, tool_name: str, params: Any) -> Optional[Dict[str, Any]]:
        """
        Get the context for a tool call.
        
        Args:
            tool_name: Name of the MCP tool
            params: Parameters passed to the tool
        
        Returns:
            Dict with session_id, agent_type, agent_confidence, etc.
            or None if no correlation found
        """
        try:
            context = retrieve_mcp_context(tool_name, params)
            
            if self._debug and context:
                print(f"[MCP Context] Found: session={context['session_id'][:8]}..., "
                      f"agent={context['agent_type']}, "
                      f"confidence={context['agent_confidence']:.2f}")
            elif self._debug:
                print(f"[MCP Context] No context found for {tool_name}")
            
            return context
            
        except Exception as e:
            if self._debug:
                print(f"[MCP Context] Error: {e}")
            return None
    
    def with_context(self, func: Callable) -> Callable:
        """
        Decorator that adds context to MCP tool functions.
        
        The decorated function should accept a 'context' keyword argument.
        
        Example:
            @mcp_context.with_context
            async def my_tool(arg1, arg2, context=None):
                if context:
                    # Use context
                    pass
        """
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Extract tool name from function
            tool_name = f"mcp_{func.__name__}"
            
            # Get params (first arg is usually params for MCP tools)
            params = args[0] if args else kwargs
            
            # Get context
            context = self.get_context(tool_name, params)
            
            # Add context to kwargs
            kwargs['context'] = context
            
            # Call original function
            return await func(*args, **kwargs)
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Extract tool name from function
            tool_name = f"mcp_{func.__name__}"
            
            # Get params (first arg is usually params for MCP tools)
            params = args[0] if args else kwargs
            
            # Get context
            context = self.get_context(tool_name, params)
            
            # Add context to kwargs
            kwargs['context'] = context
            
            # Call original function
            return func(*args, **kwargs)
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper


# Global instance for convenience
_mcp_context = MCPContext()

# Convenience functions
def get_caller_context(tool_name: str, params: Any) -> Optional[Dict[str, Any]]:
    """
    Get the calling context for an MCP tool invocation.
    
    Args:
        tool_name: Name of the MCP tool (e.g., 'mcp_firecrawl_scrape')
        params: Parameters passed to the tool
    
    Returns:
        Dict containing:
        - session_id: Claude Code session ID
        - agent_type: Type of agent (None for main, or subagent type)
        - agent_confidence: Confidence score (0.0 to 1.0)
        - project_path: Current working directory
        - correlation_age: Age of correlation in seconds
        
        Returns None if no correlation found.
    
    Example:
        context = get_caller_context('mcp_firecrawl_scrape', {'url': '...'})
        if context:
            print(f"Called by session: {context['session_id']}")
            if context['agent_type']:
                print(f"Called by agent: {context['agent_type']}")
    """
    return _mcp_context.get_context(tool_name, params)


def with_context(func: Callable) -> Callable:
    """
    Decorator that automatically adds context to MCP tool functions.
    
    Example:
        @with_context
        async def firecrawl_scrape(params, context=None):
            if context:
                session_id = context['session_id']
                agent_type = context['agent_type']
                # Use context for logging, rate limiting, etc.
            
            # Tool implementation
            return result
    """
    return _mcp_context.with_context(func)


class SessionRateLimiter:
    """
    Rate limiter that uses session context.
    
    Example:
        limiter = SessionRateLimiter(max_per_session=10, window=60)
        
        @with_context
        async def my_tool(params, context=None):
            if context and not limiter.check(context['session_id']):
                raise Exception("Rate limit exceeded for session")
    """
    
    def __init__(self, max_per_session: int, window: int = 60):
        self.max_per_session = max_per_session
        self.window = window
        self._sessions = {}
    
    def check(self, session_id: str) -> bool:
        """Check if session is within rate limit."""
        import time
        current_time = time.time()
        
        # Clean old entries
        cutoff = current_time - self.window
        self._sessions = {
            sid: times for sid, times in self._sessions.items()
            if any(t > cutoff for t in times)
        }
        
        # Check session
        if session_id not in self._sessions:
            self._sessions[session_id] = []
        
        # Filter to window
        session_times = [t for t in self._sessions[session_id] if t > cutoff]
        
        if len(session_times) >= self.max_per_session:
            return False
        
        # Add current request
        session_times.append(current_time)
        self._sessions[session_id] = session_times
        
        return True


class AgentFilter:
    """
    Filter that allows/blocks certain agents.
    
    Example:
        filter = AgentFilter(allow=['general-purpose', 'researcher'])
        
        @with_context
        async def sensitive_tool(params, context=None):
            if context and not filter.check(context['agent_type']):
                raise Exception(f"Tool not available to {context['agent_type']}")
    """
    
    def __init__(self, allow: list = None, block: list = None):
        self.allow = set(allow) if allow else None
        self.block = set(block) if block else set()
    
    def check(self, agent_type: Optional[str]) -> bool:
        """Check if agent is allowed."""
        if agent_type in self.block:
            return False
        
        if self.allow is not None:
            return agent_type in self.allow
        
        return True


# Export public API
__all__ = [
    'get_caller_context',
    'with_context',
    'MCPContext',
    'SessionRateLimiter',
    'AgentFilter'
]