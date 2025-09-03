#!/usr/bin/env python3
"""
Enhanced PreToolUse hook for Claude Code subagent tracking.
Detects Task tool invocations and tracks active subagents.
"""

import sys
import os

from database_utils import SubagentTracker, read_hook_input, write_hook_response, log_debug, extract_subagent_type
from active_subagent_tracker import ActiveSubagentTracker
from mcp_correlation_service import store_mcp_context

def main():
    """Main hook execution function."""
    try:
        # Read hook input from Claude Code
        hook_data = read_hook_input()
        
        if not hook_data:
            log_debug("No hook data received")
            write_hook_response(exit_code=0)
            return
        
        # Extract relevant information
        session_id = hook_data.get('session_id')
        tool_name = hook_data.get('tool_name')
        tool_input = hook_data.get('tool_input', {})
        transcript_path = hook_data.get('transcript_path')
        cwd = hook_data.get('cwd')
        
        log_debug(f"PreToolUse hook triggered", {
            'session_id': session_id,
            'tool_name': tool_name,
            'transcript_path': transcript_path
        })
        
        # Store correlation for MCP tools
        if tool_name and tool_name.startswith('mcp'):
            try:
                # Get current agent context
                active_tracker = ActiveSubagentTracker()
                active_agents = active_tracker.get_active_for_session(session_id)
                
                # Use most recently started agent if multiple active
                current_agent = None
                current_confidence = 0.0
                if active_agents:
                    # Sort by start time (most recent first)
                    sorted_agents = sorted(active_agents, 
                                         key=lambda a: a['started_at'], 
                                         reverse=True)
                    if sorted_agents:
                        current_agent = sorted_agents[0]['subagent_type']
                        # Confidence based on number of active agents
                        current_confidence = 1.0 / len(active_agents)
                
                # Store correlation
                correlation_id = store_mcp_context(
                    tool_name=tool_name,
                    params=tool_input,
                    session_id=session_id,
                    agent_type=current_agent,
                    agent_confidence=current_confidence,
                    project_path=cwd,
                    user_message=None  # Could extract from transcript if needed
                )
                
                log_debug(f"Stored MCP correlation: {correlation_id}", {
                    'tool_name': tool_name,
                    'session_id': session_id[:8] + '...',
                    'agent_type': current_agent,
                    'confidence': current_confidence
                })
                
            except Exception as e:
                log_debug(f"Error storing MCP correlation: {e}")
        
        # Only process Task tool calls (subagent invocations)
        if tool_name != 'Task':
            log_debug(f"Processed non-Task tool: {tool_name}")
            write_hook_response(exit_code=0)
            return
        
        # Extract subagent type from tool input
        subagent_type = extract_subagent_type(tool_input)
        
        if not subagent_type or subagent_type == 'unknown':
            log_debug("Could not extract subagent type from tool input", tool_input)
            write_hook_response(exit_code=0)
            return
        
        # Get task details
        description = tool_input.get('description', '')
        prompt = tool_input.get('prompt', '')
        
        # Initialize database tracker
        db_tracker = SubagentTracker()
        
        # Create subagent session record in database
        try:
            subagent_session_id = db_tracker.start_subagent(
                session_id=session_id,
                subagent_type=subagent_type,
                transcript_path=transcript_path,
                cwd=cwd
            )
            
            log_debug(f"Started tracking subagent in database", {
                'subagent_session_id': subagent_session_id,
                'subagent_type': subagent_type,
                'session_id': session_id
            })
            
        except Exception as e:
            log_debug(f"Error starting database tracking: {e}")
            subagent_session_id = None
        
        # Register with active subagent tracker for reliable stop detection
        try:
            active_tracker = ActiveSubagentTracker()
            
            # Try to get line number from transcript position
            task_line_number = 0
            if transcript_path and os.path.exists(transcript_path):
                try:
                    with open(transcript_path, 'r') as f:
                        task_line_number = sum(1 for _ in f)
                except:
                    pass
            
            tracking_id = active_tracker.register_start(
                session_id=session_id,
                subagent_type=subagent_type,
                description=description,
                prompt=prompt,
                task_line_number=task_line_number
            )
            
            log_debug(f"Registered active subagent", {
                'tracking_id': tracking_id,
                'subagent_type': subagent_type,
                'task_line': task_line_number
            })
            
            # Store tracking ID for potential future use
            if subagent_session_id:
                # Could store tracking_id in database for correlation
                pass
            
        except Exception as e:
            log_debug(f"Error registering active subagent: {e}")
            tracking_id = None
        
        # Provide feedback to Claude
        response = {
            "continue": True,
            "message": f"🤖 Tracking subagent '{subagent_type}' (DB: {subagent_session_id}, Track: {tracking_id})"
        }
        
        write_hook_response(response, exit_code=0)
        
    except Exception as e:
        log_debug(f"PreToolUse hook error: {e}")
        # Don't block tool execution on hook errors
        write_hook_response(exit_code=0)

if __name__ == "__main__":
    main()