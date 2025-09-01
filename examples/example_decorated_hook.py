#!/usr/bin/env python3
"""
Example showing decorator-based subagent filtering.
This hook only runs when called by specific subagents.
"""

import sys
import json
import os

sys.path.insert(0, os.path.expanduser('~/.claude/subagent-monitor/lib'))

from subagent_context import SubagentContext

# This hook only runs for code-reviewer and security-scanner subagents
@SubagentContext.require_subagent(['code-reviewer', 'security-scanner'])
def perform_security_checks(_subagent=None):
    """
    Perform security checks - only when called by review/security subagents.
    The decorator automatically adds _subagent to kwargs.
    """
    print(f"[Security Check] Running for {_subagent['type']}", file=sys.stderr)
    
    # Different checks based on subagent
    if _subagent['type'] == 'security-scanner':
        print("  ✓ Deep security scan", file=sys.stderr)
        print("  ✓ Checking for vulnerabilities", file=sys.stderr)
        print("  ✓ Analyzing dependencies", file=sys.stderr)
    else:
        print("  ✓ Basic security review", file=sys.stderr)
        print("  ✓ Code quality checks", file=sys.stderr)
    
    return {"security_check": "passed"}


def main():
    """Main hook entry point."""
    # Read hook input
    try:
        hook_data = json.loads(sys.stdin.read())
    except:
        hook_data = {}
    
    # Set session ID in environment for the decorator to use
    if 'session_id' in hook_data:
        os.environ['CLAUDE_SESSION_ID'] = hook_data['session_id']
    
    # This will only run if called by allowed subagents
    result = perform_security_checks()
    
    if result:
        # Security checks were performed
        response = {
            "continue": True,
            "message": "Security checks completed",
            **result
        }
    else:
        # Skipped (not called by allowed subagent)
        response = {"continue": True}
    
    print(json.dumps(response))
    sys.exit(0)

if __name__ == "__main__":
    main()