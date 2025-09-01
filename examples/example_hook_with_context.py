#!/usr/bin/env python3
"""
Example hook showing how to use SubagentContext to identify the calling subagent.
This could be a PreToolUse, PostToolUse, or any other hook type.
"""

import sys
import json
import os

# Add the subagent monitoring lib to path
# In production, you'd install the package or adjust the path as needed
sys.path.insert(0, os.path.expanduser('~/.claude/subagent-monitor/lib'))

from subagent_context import SubagentContext, get_calling_subagent

def main():
    """Example hook that behaves differently based on calling subagent."""
    
    # Read hook input from Claude Code
    try:
        hook_data = json.loads(sys.stdin.read())
    except:
        hook_data = {}
    
    session_id = hook_data.get('session_id')
    tool_name = hook_data.get('tool_name', 'Unknown')
    
    # Get the calling subagent context
    context = SubagentContext()
    subagent = context.get_current_subagent(session_id)
    
    if subagent:
        # We're being called by a subagent
        print(f"[Subagent Context Detected]", file=sys.stderr)
        print(f"  Type: {subagent['type']}", file=sys.stderr)
        print(f"  Confidence: {subagent['confidence']:.0%}", file=sys.stderr)
        print(f"  Tool being used: {tool_name}", file=sys.stderr)
        
        # Example: Different behavior based on subagent type
        if subagent['type'] == 'code-reviewer':
            # More strict validation for code reviewer
            if tool_name in ['Write', 'Edit']:
                print(f"⚠️  Code reviewer is modifying files - extra validation needed", file=sys.stderr)
                # Could add additional checks here
                
        elif subagent['type'] == 'test-runner':
            # Special handling for test runner
            if tool_name == 'Bash':
                print(f"🧪 Test runner executing command", file=sys.stderr)
                # Could add test isolation here
                
        elif subagent['type'] == 'general-purpose':
            # Standard handling
            print(f"📝 General purpose subagent using {tool_name}", file=sys.stderr)
            
        # Add subagent info to response for downstream processing
        response = {
            "continue": True,
            "subagent_context": {
                "type": subagent['type'],
                "confidence": subagent['confidence']
            }
        }
        
    else:
        # Direct call (not from subagent)
        print(f"[Direct Call] Tool: {tool_name}", file=sys.stderr)
        response = {"continue": True}
    
    # Output response
    print(json.dumps(response))
    sys.exit(0)

if __name__ == "__main__":
    main()