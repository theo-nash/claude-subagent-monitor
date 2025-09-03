#!/usr/bin/env python3
"""
MCP Correlation Service for mapping tool calls to session/agent context.
Enables MCPs to identify their caller without protocol modifications.
"""

import os
import json
import time
import hashlib
import sqlite3
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from threading import Lock

class MCPCorrelationService:
    """
    Service for correlating MCP tool calls with Claude Code session/agent context.
    
    Architecture:
    1. PreToolUse hook writes context with tool call fingerprint
    2. MCP queries context using same fingerprint
    3. Correlation matched within time window
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize the correlation service."""
        if db_path is None:
            # Default to shared data directory
            data_dir = os.environ.get('SUBAGENT_DATA_DIR', 
                                      os.path.expanduser('~/.claude/subagent-monitor/data'))
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, 'mcp_correlations.db')
        
        self.db_path = db_path
        self.lock = Lock()
        self._init_database()
        
        # Configuration
        self.time_window = 5.0  # seconds to match correlation
        self.cleanup_interval = 60  # seconds to keep old correlations
    
    def _init_database(self):
        """Initialize correlation database schema."""
        # Create connection and initialize schema
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS mcp_correlations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    tool_name TEXT NOT NULL,
                    param_hash TEXT NOT NULL,
                    param_preview TEXT,
                    session_id TEXT NOT NULL,
                    agent_type TEXT,
                    agent_confidence REAL,
                    matched BOOLEAN DEFAULT 0,
                    matched_at REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    
                    -- Additional context
                    project_path TEXT,
                    user_message TEXT,
                    sequence_num INTEGER,
                    
                    -- Indexing for fast lookup
                    UNIQUE(tool_name, param_hash, timestamp)
                )
            ''')
            
            # Create indexes for performance
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_correlation_lookup 
                ON mcp_correlations(tool_name, param_hash, timestamp)
            ''')
            
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_correlation_cleanup 
                ON mcp_correlations(created_at)
            ''')
            
            conn.commit()
        finally:
            conn.close()
    
    def compute_param_hash(self, params: Any) -> str:
        """
        Compute deterministic hash of parameters.
        Handles nested structures and ensures consistent ordering.
        """
        # Normalize params to ensure consistent hashing
        if params is None:
            normalized = ""
        elif isinstance(params, dict):
            # Sort keys for deterministic ordering
            normalized = json.dumps(params, sort_keys=True, separators=(',', ':'))
        elif isinstance(params, (list, tuple)):
            normalized = json.dumps(params, separators=(',', ':'))
        else:
            normalized = str(params)
        
        # Use SHA-256 for strong collision resistance
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    def store_correlation(self, 
                         tool_name: str,
                         params: Any,
                         session_id: str,
                         agent_type: Optional[str] = None,
                         agent_confidence: Optional[float] = None,
                         project_path: Optional[str] = None,
                         user_message: Optional[str] = None,
                         sequence_num: Optional[int] = None) -> str:
        """
        Store a correlation entry from PreToolUse hook.
        
        Returns:
            Correlation ID for debugging
        """
        timestamp = time.time()
        param_hash = self.compute_param_hash(params)
        
        # Create preview for debugging (first 200 chars of params)
        param_preview = str(params)[:200] if params else ""
        
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('''
                    INSERT OR REPLACE INTO mcp_correlations 
                    (timestamp, tool_name, param_hash, param_preview,
                     session_id, agent_type, agent_confidence,
                     project_path, user_message, sequence_num)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (timestamp, tool_name, param_hash, param_preview,
                      session_id, agent_type, agent_confidence,
                      project_path, user_message, sequence_num))
                
                conn.commit()
                correlation_id = f"{tool_name}:{param_hash[:8]}:{timestamp:.3f}"
                
                # Cleanup old correlations
                self._cleanup_old_correlations(conn)
                
                return correlation_id
    
    def retrieve_correlation(self, 
                           tool_name: str,
                           params: Any,
                           mark_matched: bool = True) -> Optional[Dict[str, Any]]:
        """
        Retrieve correlation context for MCP tool call.
        
        Args:
            tool_name: Name of the MCP tool
            params: Parameters passed to tool
            mark_matched: Whether to mark correlation as matched (prevents reuse)
        
        Returns:
            Context dict with session_id, agent_type, etc. or None
        """
        current_time = time.time()
        param_hash = self.compute_param_hash(params)
        
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                # Find matching correlation within time window
                cursor = conn.execute('''
                    SELECT id, timestamp, session_id, agent_type, agent_confidence,
                           project_path, user_message, sequence_num, param_preview
                    FROM mcp_correlations
                    WHERE tool_name = ?
                      AND param_hash = ?
                      AND timestamp > ?
                      AND timestamp <= ?
                      AND matched = 0
                    ORDER BY timestamp DESC
                    LIMIT 1
                ''', (tool_name, param_hash, 
                      current_time - self.time_window, current_time))
                
                row = cursor.fetchone()
                
                if row:
                    (correlation_id, timestamp, session_id, agent_type, agent_confidence,
                     project_path, user_message, sequence_num, param_preview) = row
                    
                    # Mark as matched if requested
                    if mark_matched:
                        conn.execute('''
                            UPDATE mcp_correlations
                            SET matched = 1, matched_at = ?
                            WHERE id = ?
                        ''', (current_time, correlation_id))
                        conn.commit()
                    
                    # Return context
                    return {
                        'session_id': session_id,
                        'agent_type': agent_type,
                        'agent_confidence': agent_confidence,
                        'project_path': project_path,
                        'user_message': user_message,
                        'sequence_num': sequence_num,
                        'correlation_age': current_time - timestamp,
                        'param_preview': param_preview
                    }
                
                return None
    
    def _cleanup_old_correlations(self, conn: sqlite3.Connection):
        """Remove correlations older than cleanup interval."""
        cutoff_time = time.time() - self.cleanup_interval
        conn.execute('''
            DELETE FROM mcp_correlations
            WHERE timestamp < ?
        ''', (cutoff_time,))
    
    def get_stats(self) -> Dict[str, Any]:
        """Get correlation service statistics."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(matched) as matched,
                    COUNT(DISTINCT session_id) as unique_sessions,
                    COUNT(DISTINCT agent_type) as unique_agents,
                    MIN(timestamp) as oldest,
                    MAX(timestamp) as newest
                FROM mcp_correlations
            ''')
            
            row = cursor.fetchone()
            
            current_time = time.time()
            return {
                'total_correlations': row[0],
                'matched_correlations': row[1] or 0,
                'unique_sessions': row[2],
                'unique_agents': row[3],
                'oldest_age': current_time - row[4] if row[4] else None,
                'newest_age': current_time - row[5] if row[5] else None,
                'time_window': self.time_window,
                'cleanup_interval': self.cleanup_interval
            }
    
    def debug_recent_correlations(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent correlations for debugging."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT tool_name, param_preview, session_id, agent_type,
                       matched, timestamp, matched_at
                FROM mcp_correlations
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))
            
            results = []
            current_time = time.time()
            for row in cursor:
                results.append({
                    'tool_name': row[0],
                    'param_preview': row[1][:50] + '...' if len(row[1]) > 50 else row[1],
                    'session_id': row[2][:8] + '...' if len(row[2]) > 8 else row[2],
                    'agent_type': row[3],
                    'matched': bool(row[4]),
                    'age': f"{current_time - row[5]:.1f}s ago",
                    'matched_delay': f"{row[6] - row[5]:.3f}s" if row[6] else None
                })
            
            return results


# Singleton instance for easy import
_correlation_service = None

def get_correlation_service() -> MCPCorrelationService:
    """Get or create the singleton correlation service."""
    global _correlation_service
    if _correlation_service is None:
        _correlation_service = MCPCorrelationService()
    return _correlation_service


# Convenience functions for hook integration
def store_mcp_context(tool_name: str, params: Any, session_id: str, **kwargs) -> str:
    """Store MCP correlation context from PreToolUse hook."""
    service = get_correlation_service()
    return service.store_correlation(tool_name, params, session_id, **kwargs)


def retrieve_mcp_context(tool_name: str, params: Any) -> Optional[Dict[str, Any]]:
    """Retrieve MCP correlation context from MCP server."""
    service = get_correlation_service()
    return service.retrieve_correlation(tool_name, params)