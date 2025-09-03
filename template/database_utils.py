#!/usr/bin/env python3
"""
Database utilities for Claude Code subagent tracking system.
Handles SQLite operations, schema initialization, and common queries.
"""

import sqlite3
import json
import os
import time
from typing import Dict, Any, List, Optional, Tuple
from contextlib import contextmanager

class SubagentTracker:
    def __init__(self, db_path: str = None):
        """Initialize the subagent tracker with database path."""
        if db_path is None:
            # Check for global installation first
            global_claude_dir = os.path.expanduser('~/.claude')
            if os.path.exists(global_claude_dir):
                claude_dir = global_claude_dir
            else:
                # Fall back to project-specific
                claude_dir = os.path.join(os.getcwd(), '.claude')
            
            os.makedirs(claude_dir, exist_ok=True)
            db_path = os.path.join(claude_dir, 'subagents.db')
        
        self.db_path = db_path
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        try:
            yield conn
        finally:
            conn.close()
    
    def init_database(self):
        """Initialize database with schema."""
        schema_file = os.path.join(os.path.dirname(__file__), 'schema.sql')
        
        # If schema.sql doesn't exist, create inline
        schema_sql = '''
        -- Subagent Tracking Database Schema
        CREATE TABLE IF NOT EXISTS subagent_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            subagent_type TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            start_timestamp INTEGER NOT NULL,
            end_timestamp INTEGER NULL,
            duration_seconds INTEGER NULL,
            transcript_path TEXT,
            cwd TEXT,
            total_tools_used INTEGER DEFAULT 0,
            total_messages INTEGER DEFAULT 0,
            total_tokens_estimated INTEGER DEFAULT 0,
            success_status TEXT,
            -- Enhanced statistics
            total_runtime INTEGER DEFAULT 0,
            total_turns INTEGER DEFAULT 0,
            files_created INTEGER DEFAULT 0,
            files_modified INTEGER DEFAULT 0,
            files_read INTEGER DEFAULT 0,
            files_deleted INTEGER DEFAULT 0,
            file_paths TEXT,  -- JSON array of file paths
            documentation_updated BOOLEAN DEFAULT 0,
            created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
            updated_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
            UNIQUE(session_id, subagent_type, start_timestamp)
        );

        CREATE TABLE IF NOT EXISTS subagent_tool_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subagent_session_id INTEGER NOT NULL,
            tool_name TEXT NOT NULL,
            tool_category TEXT,
            usage_count INTEGER NOT NULL DEFAULT 1,
            first_used_at INTEGER NOT NULL,
            last_used_at INTEGER NOT NULL,
            tool_metadata TEXT,
            FOREIGN KEY (subagent_session_id) REFERENCES subagent_sessions(id) ON DELETE CASCADE,
            UNIQUE(subagent_session_id, tool_name)
        );

        CREATE TABLE IF NOT EXISTS subagent_message_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subagent_session_id INTEGER NOT NULL,
            message_type TEXT NOT NULL,
            message_count INTEGER NOT NULL DEFAULT 0,
            total_chars INTEGER NOT NULL DEFAULT 0,
            avg_chars_per_message REAL DEFAULT 0,
            FOREIGN KEY (subagent_session_id) REFERENCES subagent_sessions(id) ON DELETE CASCADE,
            UNIQUE(subagent_session_id, message_type)
        );

        CREATE TABLE IF NOT EXISTS subagent_errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subagent_session_id INTEGER NOT NULL,
            error_timestamp INTEGER NOT NULL,
            error_type TEXT NOT NULL,
            error_message TEXT,
            tool_name TEXT,
            FOREIGN KEY (subagent_session_id) REFERENCES subagent_sessions(id) ON DELETE CASCADE
        );

        -- Indexes
        CREATE INDEX IF NOT EXISTS idx_subagent_sessions_session_id ON subagent_sessions(session_id);
        CREATE INDEX IF NOT EXISTS idx_subagent_sessions_active ON subagent_sessions(is_active);
        CREATE INDEX IF NOT EXISTS idx_subagent_sessions_type ON subagent_sessions(subagent_type);
        CREATE INDEX IF NOT EXISTS idx_subagent_sessions_timestamps ON subagent_sessions(start_timestamp, end_timestamp);
        CREATE INDEX IF NOT EXISTS idx_tool_usage_session ON subagent_tool_usage(subagent_session_id);
        CREATE INDEX IF NOT EXISTS idx_message_stats_session ON subagent_message_stats(subagent_session_id);
        CREATE INDEX IF NOT EXISTS idx_errors_session ON subagent_errors(subagent_session_id);

        -- Triggers
        CREATE TRIGGER IF NOT EXISTS update_subagent_duration 
        AFTER UPDATE OF end_timestamp ON subagent_sessions
        WHEN NEW.end_timestamp IS NOT NULL AND OLD.end_timestamp IS NULL
        BEGIN
            UPDATE subagent_sessions 
            SET 
                duration_seconds = NEW.end_timestamp - NEW.start_timestamp,
                updated_at = strftime('%s', 'now')
            WHERE id = NEW.id;
        END;

        CREATE TRIGGER IF NOT EXISTS update_subagent_updated_at
        AFTER UPDATE ON subagent_sessions
        BEGIN
            UPDATE subagent_sessions 
            SET updated_at = strftime('%s', 'now')
            WHERE id = NEW.id;
        END;

        -- Views
        CREATE VIEW IF NOT EXISTS active_subagents AS
        SELECT 
            s.session_id,
            s.subagent_type,
            s.start_timestamp,
            datetime(s.start_timestamp, 'unixepoch') as start_time,
            (strftime('%s', 'now') - s.start_timestamp) as running_duration_seconds,
            s.cwd,
            s.total_tools_used,
            s.total_messages
        FROM subagent_sessions s
        WHERE s.is_active = 1
        ORDER BY s.start_timestamp DESC;
        '''
        
        with self.get_connection() as conn:
            conn.executescript(schema_sql)
            conn.commit()
    
    def start_subagent(self, session_id: str, subagent_type: str, transcript_path: str = None, cwd: str = None) -> int:
        """Mark a subagent as started and return the database ID."""
        start_time = int(time.time())
        
        with self.get_connection() as conn:
            cursor = conn.execute('''
                INSERT INTO subagent_sessions 
                (session_id, subagent_type, start_timestamp, transcript_path, cwd)
                VALUES (?, ?, ?, ?, ?)
            ''', (session_id, subagent_type, start_time, transcript_path, cwd))
            
            subagent_session_id = cursor.lastrowid
            conn.commit()
            return subagent_session_id
    
    def stop_subagent(self, session_id: str, subagent_type: str, success_status: str = 'completed') -> Optional[int]:
        """Mark a subagent as stopped. Returns the subagent_session_id if found."""
        end_time = int(time.time())
        
        with self.get_connection() as conn:
            # Find the most recent active subagent of this type in this session
            cursor = conn.execute('''
                SELECT id FROM subagent_sessions 
                WHERE session_id = ? AND subagent_type = ? AND is_active = 1
                ORDER BY start_timestamp DESC
                LIMIT 1
            ''', (session_id, subagent_type))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            subagent_session_id = row[0]
            
            # Update the subagent as stopped
            conn.execute('''
                UPDATE subagent_sessions 
                SET 
                    is_active = 0,
                    end_timestamp = ?,
                    success_status = ?,
                    updated_at = strftime('%s', 'now')
                WHERE id = ?
            ''', (end_time, success_status, subagent_session_id))
            
            conn.commit()
            return subagent_session_id
    
    def update_statistics(self, subagent_session_id: int, 
                         tool_stats: Dict[str, int] = None,
                         message_stats: Dict[str, Dict[str, int]] = None,
                         total_tokens: int = None,
                         enhanced_stats: Dict[str, Any] = None):
        """Update tool usage and message statistics for a subagent session."""
        
        with self.get_connection() as conn:
            # Update main session with totals
            if tool_stats or message_stats or total_tokens or enhanced_stats:
                updates = []
                params = []
                
                if tool_stats:
                    total_tools = sum(tool_stats.values())
                    updates.append("total_tools_used = ?")
                    params.append(total_tools)
                
                if message_stats:
                    total_messages = sum(stats['count'] for stats in message_stats.values())
                    updates.append("total_messages = ?")
                    params.append(total_messages)
                
                if total_tokens:
                    updates.append("total_tokens_estimated = ?")
                    params.append(total_tokens)
                
                # Add enhanced statistics
                if enhanced_stats:
                    if 'total_runtime' in enhanced_stats:
                        updates.append("total_runtime = ?")
                        params.append(enhanced_stats['total_runtime'])
                    
                    if 'total_turns' in enhanced_stats:
                        updates.append("total_turns = ?")
                        params.append(enhanced_stats['total_turns'])
                    
                    if 'files_created' in enhanced_stats:
                        updates.append("files_created = ?")
                        params.append(enhanced_stats['files_created'])
                    
                    if 'files_modified' in enhanced_stats:
                        updates.append("files_modified = ?")
                        params.append(enhanced_stats['files_modified'])
                    
                    if 'files_read' in enhanced_stats:
                        updates.append("files_read = ?")
                        params.append(enhanced_stats['files_read'])
                    
                    if 'files_deleted' in enhanced_stats:
                        updates.append("files_deleted = ?")
                        params.append(enhanced_stats['files_deleted'])
                    
                    if 'file_paths' in enhanced_stats:
                        # Store as JSON array
                        updates.append("file_paths = ?")
                        params.append(json.dumps(enhanced_stats['file_paths']))
                    
                    if 'documentation_updated' in enhanced_stats:
                        updates.append("documentation_updated = ?")
                        params.append(1 if enhanced_stats['documentation_updated'] else 0)
                
                if updates:
                    params.append(subagent_session_id)
                    conn.execute(f'''
                        UPDATE subagent_sessions 
                        SET {', '.join(updates)}
                        WHERE id = ?
                    ''', params)
            
            # Insert/update tool usage stats
            if tool_stats:
                for tool_name, count in tool_stats.items():
                    current_time = int(time.time())
                    conn.execute('''
                        INSERT INTO subagent_tool_usage 
                        (subagent_session_id, tool_name, usage_count, first_used_at, last_used_at)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(subagent_session_id, tool_name) DO UPDATE SET
                            usage_count = usage_count + excluded.usage_count,
                            last_used_at = excluded.last_used_at
                    ''', (subagent_session_id, tool_name, count, current_time, current_time))
            
            # Insert/update message statistics
            if message_stats:
                for msg_type, stats in message_stats.items():
                    count = stats.get('count', 0)
                    total_chars = stats.get('total_chars', 0)
                    avg_chars = total_chars / count if count > 0 else 0
                    
                    conn.execute('''
                        INSERT INTO subagent_message_stats 
                        (subagent_session_id, message_type, message_count, total_chars, avg_chars_per_message)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(subagent_session_id, message_type) DO UPDATE SET
                            message_count = excluded.message_count,
                            total_chars = excluded.total_chars,
                            avg_chars_per_message = excluded.avg_chars_per_message
                    ''', (subagent_session_id, msg_type, count, total_chars, avg_chars))
            
            conn.commit()
    
    def log_error(self, subagent_session_id: int, error_type: str, error_message: str, tool_name: str = None):
        """Log an error for a subagent session."""
        with self.get_connection() as conn:
            conn.execute('''
                INSERT INTO subagent_errors 
                (subagent_session_id, error_timestamp, error_type, error_message, tool_name)
                VALUES (?, ?, ?, ?, ?)
            ''', (subagent_session_id, int(time.time()), error_type, error_message, tool_name))
            conn.commit()
    
    def get_active_subagents(self) -> List[Dict[str, Any]]:
        """Get all currently active subagents."""
        with self.get_connection() as conn:
            cursor = conn.execute('SELECT * FROM active_subagents')
            return [dict(row) for row in cursor.fetchall()]
    
    def get_subagent_details(self, session_id: str, subagent_type: str = None) -> List[Dict[str, Any]]:
        """Get detailed information about subagents in a session."""
        with self.get_connection() as conn:
            if subagent_type:
                cursor = conn.execute('''
                    SELECT * FROM subagent_summary 
                    WHERE session_id = ? AND subagent_type = ?
                    ORDER BY start_time DESC
                ''', (session_id, subagent_type))
            else:
                cursor = conn.execute('''
                    SELECT * FROM subagent_summary 
                    WHERE session_id = ?
                    ORDER BY start_time DESC
                ''', (session_id,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def cleanup_old_sessions(self, days_old: int = 30):
        """Clean up sessions older than specified days."""
        cutoff_time = int(time.time()) - (days_old * 24 * 60 * 60)
        
        with self.get_connection() as conn:
            cursor = conn.execute('''
                DELETE FROM subagent_sessions 
                WHERE start_timestamp < ? AND is_active = 0
            ''', (cutoff_time,))
            
            deleted_count = cursor.rowcount
            conn.commit()
            return deleted_count

def categorize_tool(tool_name: str) -> str:
    """Categorize tools into logical groups."""
    tool_categories = {
        'file': ['Read', 'Write', 'Edit', 'MultiEdit', 'Create', 'Move', 'Delete'],
        'web': ['WebSearch', 'WebFetch'],
        'command': ['Bash', 'Shell', 'Command'],
        'code': ['Notebook', 'Debug', 'Test', 'Lint'],
        'git': ['GitAdd', 'GitCommit', 'GitPush', 'GitStatus'],
        'search': ['Grep', 'Find', 'Glob'],
        'subagent': ['Task'],
        'mcp': []  # Will be filled with MCP tools dynamically
    }
    
    # Handle MCP tools (pattern: mcp__<server>__<tool>)
    if tool_name.startswith('mcp__'):
        return 'mcp'
    
    # Check standard categories
    for category, tools in tool_categories.items():
        if tool_name in tools:
            return category
    
    return 'other'

def extract_subagent_type(tool_input: Dict[str, Any]) -> Optional[str]:
    """Extract subagent type from Task tool input."""
    # Task tool typically has structure like:
    # {"task": "Use the code-reviewer subagent to check...", "subagent": "code-reviewer"}
    # or {"subagent_type": "sdk-protocol-specialist", "description": "...", "prompt": "..."}
    # or the subagent name might be embedded in the task description
    
    # Check for explicit subagent_type field (used in newer format)
    if 'subagent_type' in tool_input:
        return tool_input['subagent_type']
    
    # Check for subagent field (older format)
    if 'subagent' in tool_input:
        return tool_input['subagent']
    
    if 'task' in tool_input:
        task_text = tool_input['task'].lower()
        # Look for patterns like "use the X subagent" or "invoke X agent"
        import re
        patterns = [
            r'use\s+the\s+([a-zA-Z0-9\-_]+)\s+subagent',
            r'invoke\s+([a-zA-Z0-9\-_]+)\s+agent',
            r'call\s+([a-zA-Z0-9\-_]+)\s+subagent',
            r'run\s+([a-zA-Z0-9\-_]+)\s+agent'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, task_text)
            if match:
                return match.group(1)
    
    # Fallback: return a hash of the task or 'unknown'
    if 'task' in tool_input:
        import hashlib
        task_hash = hashlib.md5(tool_input['task'].encode()).hexdigest()[:8]
        return f"unknown-{task_hash}"
    
    return 'unknown'

# Utility functions for Claude Code hook integration
def read_hook_input() -> Dict[str, Any]:
    """Read JSON input from stdin (Claude Code hook format)."""
    import sys
    try:
        return json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        print(f"Error parsing hook input: {e}", file=sys.stderr)
        return {}

def write_hook_response(response: Dict[str, Any] = None, exit_code: int = 0):
    """Write hook response and exit with specified code."""
    import sys
    
    if response:
        print(json.dumps(response))
    
    sys.exit(exit_code)

def log_debug(message: str, data: Dict[str, Any] = None):
    """Log debug information to stderr for Claude Code."""
    import sys
    
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    log_msg = f"[{timestamp}] SUBAGENT_TRACKER: {message}"
    
    if data:
        log_msg += f" | Data: {json.dumps(data, indent=2)}"
    
    print(log_msg, file=sys.stderr)