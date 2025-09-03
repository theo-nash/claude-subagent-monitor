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
│   │   └── ...
│   ├── data/                        # Database and state files
│   │   ├── subagents.db
│   │   └── active_subagents.json
│   ├── bin/                         # Query command
│   │   └── subagent-query
│   └── README.md
├── subagent → subagent-monitor/bin/subagent-query  # Convenient symlink
└── settings.json                    # Hook configuration (only external file)
```

## 🔧 Features

- **Robust Detection**: Multi-strategy subagent identification with confidence scoring
- **UUID Chain Reconstruction**: Accurate extraction of subagent conversations from transcripts
- **Enhanced Statistics**: Tracks runtime, conversation turns, and file operations
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
│   ├── pretooluse_subagent_tracker.py  # PreToolUse hook
│   └── subagentstop_tracker.py     # SubagentStop hook
├── examples/                        # Example hook integrations
│   ├── example_hook_with_context.py
│   └── example_decorated_hook.py
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

## 🛠️ Development

The package uses relative imports internally and sets up paths correctly at each entry point:
- Hooks set `SUBAGENT_DATA_DIR` environment variable
- All components use the same data directory
- Import paths maintained through sys.path injection

## 📝 License

MIT