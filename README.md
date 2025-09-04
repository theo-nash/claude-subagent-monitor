# Claude Subagent Monitoring System

A self-contained monitoring system for Claude Code subagents that tracks Task tool invocations, analyzes subagent conversations, and provides detailed statistics.

## 🚀 Quick Start

```bash
python3 install.py
```

Choose:
1. **Global install** (`~/.claude/subagent-monitor/`) - Recommended
2. **Project install** (`./.claude/subagent-monitor/`) - Project-specific

## 📁 Self-Contained Installation

Everything installs to a single `subagent-monitor/` directory:

```
~/.claude/                           # or ./.claude/ for project install
├── subagent-monitor/                # Everything contained here
│   ├── hooks/                       # Clean hook entry points (2 files only)
│   │   ├── pretooluse.py
│   │   └── subagentstop.py
│   ├── lib/                         # All implementation modules
│   │   ├── database_utils.py
│   │   ├── active_subagent_tracker.py
│   │   ├── robust_subagent_detector.py
│   │   ├── sidechain_reconstructor.py
│   │   ├── transcript_parser.py
│   │   ├── enhanced_stats_analyzer.py
│   │   ├── mcp_context.py
│   │   ├── mcp_correlation_service.py
│   │   ├── subagent_context.py
│   │   └── ...
│   ├── data/                        # Database and state files
│   │   ├── subagents.db
│   │   └── active_subagents.json
│   ├── bin/                         # Query command
│   │   └── subagent-query
│   └── README.md
├── subagent → subagent-monitor/bin/subagent-query  # Query command symlink
├── mcp_context.py → subagent-monitor/lib/mcp_context.py  # Developer symlink
├── subagent_context.py → subagent-monitor/lib/subagent_context.py  # Developer symlink
├── mcp_correlation_service.py → subagent-monitor/lib/mcp_correlation_service.py  # Developer symlink
└── settings.json                    # Hook configuration (only external file)
```

## 🔧 Features

- **Robust Detection**: Multi-strategy subagent identification with confidence scoring
- **UUID Chain Reconstruction**: Accurate extraction of subagent conversations from transcripts
- **Enhanced Statistics**: Tracks runtime, conversation turns, and file operations
- **MCP Context Correlation**: Enables MCPs to identify calling session and agent
- **Concurrent Support**: Handles multiple active subagents simultaneously
- **SQLite Database**: Persistent storage with detailed statistics
- **Active Tracking**: Real-time state management across hook invocations
- **Clean Installation**: Everything in one directory, no pollution
- **High Performance**: Processes 15,400+ messages/second with 100% reliability

## 📊 Usage

After installation and restarting Claude Code:

```bash
# Check active subagents
~/.claude/subagent status

# List active subagents
~/.claude/subagent active
```

## 🚀 Developer Quick Start

After installation, key libraries are symlinked to `~/.claude/` for easy access:

### For MCP Developers
```python
# Add to your MCP server
import sys
import os
sys.path.insert(0, os.path.expanduser('~/.claude'))
from mcp_context import get_caller_context, with_context

# Get session/agent context for any tool
@with_context
async def my_mcp_tool(params, context=None):
    if context:
        session_id = context['session_id']
        agent_type = context['agent_type']
        # Apply per-session logic, rate limiting, etc.
    return {"result": "success"}
```

### For Hook Developers
```python
# Add to your custom hook
import sys
import os
sys.path.insert(0, os.path.expanduser('~/.claude'))
from subagent_context import get_current_subagent

def my_hook(hook_data):
    session_id = hook_data.get('session_id')
    subagent = get_current_subagent(session_id)
    
    if subagent == 'code-reviewer':
        # Apply special logic for code review agent
        pass
```

### Available Developer Files
After installation, these files are available at `~/.claude/`:
- `mcp_context.py` - MCP context correlation helper
- `subagent_context.py` - Subagent detection for hooks
- `mcp_correlation_service.py` - Advanced correlation engine

No package installation needed - just add `~/.claude` to your Python path!

## 🗂️ Repository Structure

```
claude-subagent-monitoring/
├── install.py                       # Self-contained installer
├── template/                        # Template files for installation
│   ├── __init__.py
│   ├── database_utils.py           # Database operations
│   ├── active_subagent_tracker.py  # Active state tracking
│   ├── robust_subagent_detector.py # Detection logic
│   ├── sidechain_reconstructor.py  # UUID chain reconstruction
│   ├── transcript_parser.py        # Main transcript parser with UUID chains
│   ├── enhanced_stats_analyzer.py  # Statistics analyzer for subagents
│   ├── subagent_context.py         # API for other hooks
│   ├── mcp_correlation_service.py  # MCP context correlation engine
│   ├── mcp_context.py              # MCP helper library
│   ├── pretooluse_subagent_tracker.py  # PreToolUse hook
│   └── subagentstop_tracker.py     # SubagentStop hook
├── examples/                        # Example hook integrations
│   ├── example_hook_with_context.py
│   ├── example_decorated_hook.py
│   └── example_mcp_server.py       # MCP server with context awareness
├── test_all_transcripts.py         # Comprehensive test suite
└── README.md                        # This file
```

## 🧹 Uninstall

To completely remove the monitoring system:

```bash
# Remove the self-contained directory
rm -rf ~/.claude/subagent-monitor
rm ~/.claude/subagent

# Edit ~/.claude/settings.json to remove hook entries
```

## 🔌 API for Other Hooks

The monitoring system provides a simple API for other hooks to identify the calling subagent:

### Quick Start

```python
from subagent_context import get_calling_subagent

# In your hook
subagent_type = get_calling_subagent(session_id)
if subagent_type == 'code-reviewer':
    # Apply stricter validation
    pass
```

### Full Context API

```python
from subagent_context import SubagentContext

context = SubagentContext()
subagent = context.get_current_subagent(session_id)

if subagent:
    print(f"Called by: {subagent['type']}")
    print(f"Confidence: {subagent['confidence']}")
    print(f"Description: {subagent['description']}")
```

### Decorator for Subagent-Specific Hooks

```python
from subagent_context import SubagentContext

@SubagentContext.require_subagent(['code-reviewer', 'test-runner'])
def my_hook_function(_subagent=None):
    # This only runs when called by specified subagents
    print(f"Running for {_subagent['type']}")
```

### Use Cases

1. **Different validation rules** based on subagent type
2. **Resource limits** for certain subagents
3. **Audit logging** with subagent attribution
4. **Feature flags** per subagent type
5. **Security policies** based on calling context

See the `examples/` directory for complete hook examples.

## 🔍 How It Works

1. **PreToolUse Hook**: Detects when Task tool is invoked
   - Registers subagent in database
   - Tracks active state for reliable stop detection

2. **SubagentStop Hook**: Fires when a subagent completes
   - Uses robust detection to identify which subagent stopped
   - Confidence scoring (0.0-1.0) for reliability
   - Parses transcript for detailed statistics
   - Collects enhanced metrics: runtime, turns, file operations

3. **Data Storage**: All data stored in `subagent-monitor/data/`
   - SQLite database for history
   - JSON file for active state
   - Shared across all components

## 📈 Detection Confidence

The system uses multi-factor scoring:
- **1.0**: Only one active subagent (certain)
- **0.9**: Transcript confirms subagent type
- **0.7**: Multiple active but clear winner
- **0.5**: Multiple active and uncertain

## 📊 Enhanced Statistics

The system tracks comprehensive metrics for each subagent:

### Metrics Collected
- **Runtime**: Total conversation duration in seconds
- **Conversation Turns**: Number of user/assistant exchanges
- **File Operations**:
  - Files created (new files written)
  - Files modified (existing files edited)
  - Files read (files accessed)
  - Files deleted (files removed)
- **File Paths**: All files touched during execution
- **Documentation**: Whether any .md files were updated

### Performance
- Processes 15,400+ messages per second
- 100% success rate across all transcript formats
- Handles both main chain and sidechain message structures

## 💻 Developer Integration Guide

The monitoring system provides powerful APIs for developers building MCPs and hooks. After installation, key libraries are automatically available at `~/.claude/`.

### Zero-Configuration Setup

```python
# Just add this to any Python file:
import sys
import os
sys.path.insert(0, os.path.expanduser('~/.claude'))

# Now import what you need:
from mcp_context import get_caller_context       # For MCP developers
from subagent_context import get_current_subagent # For hook developers
```

### Example: Session-Aware MCP Tool

```python
#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.expanduser('~/.claude'))
from mcp_context import with_context

@with_context
async def fetch_url(params, context=None):
    """Fetches URL with automatic session tracking."""
    url = params['url']
    
    if context:
        # You have access to:
        # - context['session_id']     # Unique session identifier
        # - context['agent_type']     # e.g., 'researcher', 'code-reviewer'
        # - context['agent_confidence'] # 0.0 to 1.0
        # - context['project_path']   # Current working directory
        
        print(f"Fetching {url} for session {context['session_id']}")
        
        # Implement per-session caching
        cache_key = f"{context['session_id']}:{url}"
        if cached := cache.get(cache_key):
            return cached
    
    result = await do_fetch(url)
    
    if context:
        cache.set(cache_key, result)
    
    return result
```

### Example: Agent-Aware Hook

```python
#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.expanduser('~/.claude'))
from subagent_context import get_current_subagent

def pre_write_hook(hook_data):
    """Hook that applies different rules based on calling agent."""
    session_id = hook_data.get('session_id')
    file_path = hook_data.get('file_path')
    
    # Identify the calling agent
    agent = get_current_subagent(session_id)
    
    if agent == 'code-reviewer':
        # Stricter validation for code review agent
        if not run_security_checks(file_path):
            return {"block": True, "reason": "Security check failed"}
    
    elif agent == 'documentation-writer':
        # Auto-format markdown for docs agent
        format_markdown(file_path)
    
    return {"continue": True}
```

### Graceful Fallbacks

All APIs are designed to work even if the monitoring system isn't installed:

```python
from mcp_context import get_caller_context

context = get_caller_context('my_tool', params)
if context:
    # Enhanced behavior with context
    session_id = context['session_id']
else:
    # Fallback behavior without context
    session_id = 'unknown'
```

### Testing Your Integration

```python
# Test if context is available
from mcp_context import get_caller_context

def test_context():
    test_params = {'test': True}
    context = get_caller_context('test_tool', test_params)
    
    if context:
        print(f"✅ Context available: {context}")
    else:
        print("❌ No context - monitoring system may not be installed")

if __name__ == "__main__":
    test_context()
```

## 🔌 MCP Context Correlation

The system provides a groundbreaking solution for MCP servers to identify their calling context without protocol changes.

### The Problem
MCP servers receive only tool names and parameters, with no access to:
- Session IDs
- Agent context
- Claude Code internals

### The Solution
A correlation-based approach using parameter fingerprinting:
1. PreToolUse hook stores tool call with session/agent context
2. MCP computes same parameter hash
3. Context retrieved within 5-second window
4. Enables session-aware and agent-aware MCP behavior

### MCP Integration

```python
# In your MCP server
from mcp_context import get_caller_context, with_context

# Simple usage
def my_mcp_tool(params):
    context = get_caller_context('mcp_my_tool', params)
    if context:
        session_id = context['session_id']
        agent_type = context['agent_type']
        # Apply per-session rate limits, agent-specific logic, etc.

# Decorator usage  
@with_context
async def my_mcp_tool(params, context=None):
    if context and context['agent_type'] == 'researcher':
        # Provide enhanced data for researchers
        pass
```

### Features
- **Zero protocol changes**: Works with existing MCP implementations
- **Session identification**: Track usage per Claude Code session
- **Agent awareness**: Different behavior based on calling agent
- **Rate limiting**: Apply per-session limits
- **Access control**: Restrict tools to specific agents
- **Performance**: 7,000+ correlations/second retrieval

### Use Cases
- Per-session rate limiting
- Agent-specific tool behavior
- Session-aware caching
- Context-aware logging
- Security policies based on caller

## 🛠️ Development

The package uses relative imports internally and sets up paths correctly at each entry point:
- Hooks set `SUBAGENT_DATA_DIR` environment variable
- All components use the same data directory
- Import paths maintained through sys.path injection

## 📝 License

MIT