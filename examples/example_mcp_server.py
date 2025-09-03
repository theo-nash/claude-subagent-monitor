#!/usr/bin/env python3
"""
Example MCP server that uses context correlation to identify callers.

This demonstrates how an MCP can:
1. Identify which session is calling
2. Identify which agent (main/subagent) is calling
3. Apply different behavior based on caller
4. Rate limit per session
5. Log with session/agent attribution
"""

import asyncio
import json
from typing import Dict, Any, Optional
from datetime import datetime

# Import the MCP context helper
from mcp_context import (
    get_caller_context, 
    with_context, 
    SessionRateLimiter, 
    AgentFilter
)

# Example rate limiter (10 requests per minute per session)
rate_limiter = SessionRateLimiter(max_per_session=10, window=60)

# Example agent filter (only allow certain agents for sensitive operations)
sensitive_filter = AgentFilter(allow=['security-auditor', 'admin-agent'])

# Logging with context
class ContextualLogger:
    def __init__(self, name: str):
        self.name = name
    
    def log(self, message: str, context: Optional[Dict[str, Any]] = None):
        timestamp = datetime.now().isoformat()
        
        if context:
            session = context['session_id'][:8] if context.get('session_id') else 'unknown'
            agent = context.get('agent_type', 'main')
            confidence = context.get('agent_confidence', 0.0)
            
            print(f"[{timestamp}] [{self.name}] [Session: {session}] [Agent: {agent} ({confidence:.1f})] {message}")
        else:
            print(f"[{timestamp}] [{self.name}] [No context] {message}")

logger = ContextualLogger("ExampleMCP")


class ExampleMCPServer:
    """Example MCP server with context awareness."""
    
    @with_context
    async def mcp_example_fetch(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None):
        """
        Example tool that fetches data with context awareness.
        """
        url = params.get('url', '')
        
        # Log with context
        logger.log(f"Fetch requested for: {url}", context)
        
        # Apply rate limiting per session
        if context:
            session_id = context['session_id']
            if not rate_limiter.check(session_id):
                logger.log(f"Rate limit exceeded!", context)
                return {"error": "Rate limit exceeded for your session"}
        
        # Different behavior based on agent
        if context and context.get('agent_type'):
            agent = context['agent_type']
            
            if agent == 'researcher':
                # Researchers get more detailed data
                logger.log("Providing detailed data for researcher", context)
                return {
                    "url": url,
                    "data": "Detailed research data...",
                    "metadata": {"source": "academic", "citations": 5}
                }
            
            elif agent == 'code-reviewer':
                # Code reviewers get security-focused data
                logger.log("Providing security analysis for code reviewer", context)
                return {
                    "url": url,
                    "data": "Security analysis...",
                    "vulnerabilities": []
                }
        
        # Default response
        logger.log("Providing standard data", context)
        return {
            "url": url,
            "data": "Standard data..."
        }
    
    @with_context
    async def mcp_example_sensitive_operation(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None):
        """
        Example of a sensitive operation that only certain agents can perform.
        """
        operation = params.get('operation', '')
        
        logger.log(f"Sensitive operation requested: {operation}", context)
        
        # Check if agent is allowed
        if context:
            agent = context.get('agent_type')
            if not sensitive_filter.check(agent):
                logger.log(f"Access denied for agent: {agent}", context)
                return {
                    "error": f"Operation '{operation}' not permitted for agent type '{agent}'"
                }
        else:
            # No context means we can't verify - deny by default
            logger.log("Access denied - no context", context)
            return {"error": "Cannot verify caller identity"}
        
        # Perform sensitive operation
        logger.log(f"Executing sensitive operation: {operation}", context)
        return {
            "status": "success",
            "operation": operation,
            "result": "Sensitive operation completed"
        }
    
    def mcp_example_manual_context(self, params: Dict[str, Any]):
        """
        Example of manually retrieving context (without decorator).
        """
        # Manually get context
        context = get_caller_context('mcp_example_manual_context', params)
        
        if context:
            session_id = context['session_id']
            agent_type = context.get('agent_type', 'main')
            confidence = context['agent_confidence']
            
            # Use context information
            result = {
                "message": f"Hello from session {session_id[:8]}!",
                "agent": agent_type,
                "confidence": confidence
            }
            
            # Log correlation details for debugging
            if context.get('correlation_age'):
                result['debug'] = {
                    'correlation_age': f"{context['correlation_age']:.3f}s",
                    'project': context.get('project_path', 'unknown')
                }
            
            logger.log("Manual context retrieval successful", context)
            return result
        else:
            logger.log("No context available", None)
            return {
                "message": "Hello, anonymous caller!",
                "note": "Context not available"
            }


# Example usage with session tracking
class SessionTracker:
    """Track statistics per session."""
    
    def __init__(self):
        self.sessions = {}
    
    @with_context
    def track_request(self, tool_name: str, params: Any, context: Optional[Dict[str, Any]] = None):
        """Track request with session context."""
        if context and context.get('session_id'):
            session_id = context['session_id']
            
            if session_id not in self.sessions:
                self.sessions[session_id] = {
                    'first_seen': datetime.now(),
                    'last_seen': datetime.now(),
                    'request_count': 0,
                    'agents': set(),
                    'tools': []
                }
            
            session_data = self.sessions[session_id]
            session_data['last_seen'] = datetime.now()
            session_data['request_count'] += 1
            
            if context.get('agent_type'):
                session_data['agents'].add(context['agent_type'])
            
            session_data['tools'].append({
                'tool': tool_name,
                'timestamp': datetime.now(),
                'agent': context.get('agent_type')
            })
            
            logger.log(f"Session {session_id[:8]} - Request #{session_data['request_count']}", context)
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get statistics about all sessions."""
        return {
            'total_sessions': len(self.sessions),
            'sessions': [
                {
                    'session_id': sid[:8] + '...',
                    'requests': data['request_count'],
                    'agents': list(data['agents']),
                    'duration': (data['last_seen'] - data['first_seen']).total_seconds()
                }
                for sid, data in self.sessions.items()
            ]
        }


# Example of testing the correlation
async def test_correlation():
    """Test the MCP context correlation."""
    server = ExampleMCPServer()
    
    # Test parameters
    test_params = {'url': 'https://example.com'}
    
    print("\n=== Testing MCP Context Correlation ===\n")
    
    # Test 1: Fetch with context
    print("Test 1: Fetch with decorator")
    result = await server.mcp_example_fetch(test_params)
    print(f"Result: {json.dumps(result, indent=2)}\n")
    
    # Test 2: Manual context
    print("Test 2: Manual context retrieval")
    result = server.mcp_example_manual_context(test_params)
    print(f"Result: {json.dumps(result, indent=2)}\n")
    
    # Test 3: Sensitive operation
    print("Test 3: Sensitive operation")
    sensitive_params = {'operation': 'delete_all'}
    result = await server.mcp_example_sensitive_operation(sensitive_params)
    print(f"Result: {json.dumps(result, indent=2)}\n")


if __name__ == "__main__":
    # Run test
    asyncio.run(test_correlation())