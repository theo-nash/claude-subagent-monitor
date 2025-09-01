#!/usr/bin/env python3
"""
Active Subagent Tracker for reliable SubagentStop identification.
Maintains real-time state of active subagents across hook invocations.
"""

import json
import os
import time
import fcntl
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime

@dataclass
class ActiveSubagent:
    """Represents an active subagent."""
    tracking_id: str
    session_id: str
    subagent_type: str
    description: str
    start_timestamp: int
    last_seen_timestamp: int
    task_line_number: int
    prompt_hash: str  # Hash of prompt for matching
    status: str = "active"  # active, completing, completed
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ActiveSubagent':
        return cls(**data)


class ActiveSubagentTracker:
    """
    Tracks active subagents across hook invocations.
    Uses file-based persistence for cross-process communication.
    """
    
    def __init__(self, state_file: str = None):
        if state_file is None:
            # Check for global installation first
            global_claude_dir = os.path.expanduser('~/.claude')
            if os.path.exists(global_claude_dir):
                claude_dir = global_claude_dir
            else:
                # Fall back to project-specific
                claude_dir = os.path.join(os.getcwd(), '.claude')
            
            os.makedirs(claude_dir, exist_ok=True)
            state_file = os.path.join(claude_dir, 'active_subagents.json')
        
        self.state_file = state_file
        self.lock_file = state_file + '.lock'
        
    def _read_state(self) -> Dict[str, List[Dict]]:
        """Read current state from file with locking."""
        if not os.path.exists(self.state_file):
            return {"active_subagents": [], "last_updated": 0}
        
        with open(self.lock_file, 'w') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_SH)
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {"active_subagents": [], "last_updated": 0}
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    
    def _write_state(self, state: Dict[str, Any]):
        """Write state to file with locking."""
        with open(self.lock_file, 'w') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                state["last_updated"] = int(time.time())
                with open(self.state_file, 'w') as f:
                    json.dump(state, f, indent=2)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    
    def register_start(self, session_id: str, subagent_type: str, 
                      description: str, prompt: str, 
                      task_line_number: int = 0) -> str:
        """
        Register a new subagent start.
        Returns a unique tracking ID.
        """
        import hashlib
        import uuid
        
        # Generate tracking ID
        tracking_id = str(uuid.uuid4())[:8]
        
        # Hash the prompt for later matching
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:16]
        
        # Create active subagent record
        active_subagent = ActiveSubagent(
            tracking_id=tracking_id,
            session_id=session_id,
            subagent_type=subagent_type,
            description=description,
            start_timestamp=int(time.time()),
            last_seen_timestamp=int(time.time()),
            task_line_number=task_line_number,
            prompt_hash=prompt_hash,
            status="active"
        )
        
        # Update state
        state = self._read_state()
        state["active_subagents"].append(active_subagent.to_dict())
        
        # Clean up old entries (older than 1 hour)
        cutoff = int(time.time()) - 3600
        state["active_subagents"] = [
            s for s in state["active_subagents"]
            if s["last_seen_timestamp"] > cutoff or s["status"] == "active"
        ]
        
        self._write_state(state)
        
        return tracking_id
    
    def get_active_subagents(self, session_id: str = None) -> List[ActiveSubagent]:
        """Get all active subagents, optionally filtered by session."""
        state = self._read_state()
        subagents = []
        
        for data in state["active_subagents"]:
            if data["status"] == "active":
                if session_id is None or data["session_id"] == session_id:
                    subagents.append(ActiveSubagent.from_dict(data))
        
        return subagents
    
    def update_last_seen(self, tracking_id: str):
        """Update the last seen timestamp for a subagent."""
        state = self._read_state()
        
        for subagent in state["active_subagents"]:
            if subagent["tracking_id"] == tracking_id:
                subagent["last_seen_timestamp"] = int(time.time())
                break
        
        self._write_state(state)
    
    def mark_completing(self, tracking_id: str):
        """Mark a subagent as completing (SubagentStop detected)."""
        state = self._read_state()
        
        for subagent in state["active_subagents"]:
            if subagent["tracking_id"] == tracking_id:
                subagent["status"] = "completing"
                subagent["last_seen_timestamp"] = int(time.time())
                break
        
        self._write_state(state)
    
    def mark_completed(self, tracking_id: str):
        """Mark a subagent as completed."""
        state = self._read_state()
        
        for subagent in state["active_subagents"]:
            if subagent["tracking_id"] == tracking_id:
                subagent["status"] = "completed"
                subagent["last_seen_timestamp"] = int(time.time())
                break
        
        self._write_state(state)
    
    def find_likely_stopped_subagent(self, session_id: str, 
                                     transcript_hints: Dict[str, Any] = None) -> Optional[ActiveSubagent]:
        """
        Determine which subagent likely stopped based on multiple signals.
        
        Args:
            session_id: Current session ID
            transcript_hints: Optional hints from transcript analysis
                - last_sidechain_line: Line number of last sidechain message
                - last_sidechain_type: Detected subagent type from transcript
                - completion_patterns: Any completion patterns found
        
        Returns:
            The most likely stopped subagent, or None
        """
        active_subagents = self.get_active_subagents(session_id)
        
        if not active_subagents:
            return None
        
        if len(active_subagents) == 1:
            # Only one active, must be it
            return active_subagents[0]
        
        # Score each candidate
        candidates = []
        for subagent in active_subagents:
            score = 0
            reasons = []
            
            # Time-based scoring (most recently started might be completing)
            age = int(time.time()) - subagent.start_timestamp
            if age < 60:  # Started less than 1 minute ago
                score += 1
                reasons.append("recently_started")
            
            # Check against transcript hints
            if transcript_hints:
                # Match subagent type
                if transcript_hints.get("last_sidechain_type") == subagent.subagent_type:
                    score += 3
                    reasons.append("type_match")
                
                # Line number proximity (if available)
                if "last_sidechain_line" in transcript_hints:
                    line_diff = abs(transcript_hints["last_sidechain_line"] - subagent.task_line_number)
                    if line_diff < 100:  # Within 100 lines
                        score += 2
                        reasons.append("line_proximity")
            
            # LIFO assumption - most recent usually completes first
            if subagent == active_subagents[-1]:
                score += 1
                reasons.append("most_recent")
            
            candidates.append((subagent, score, reasons))
        
        # Sort by score
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        if candidates and candidates[0][1] > 0:
            winner = candidates[0][0]
            print(f"Selected {winner.subagent_type} (score: {candidates[0][1]}, reasons: {candidates[0][2]})")
            return winner
        
        # Fallback: return most recently started
        return active_subagents[-1]
    
    def cleanup_stale_entries(self, max_age_seconds: int = 3600):
        """Remove stale entries older than max_age."""
        state = self._read_state()
        cutoff = int(time.time()) - max_age_seconds
        
        state["active_subagents"] = [
            s for s in state["active_subagents"]
            if s["last_seen_timestamp"] > cutoff
        ]
        
        self._write_state(state)
    
    def get_tracking_summary(self) -> Dict[str, Any]:
        """Get a summary of current tracking state."""
        state = self._read_state()
        
        active_count = sum(1 for s in state["active_subagents"] if s["status"] == "active")
        completing_count = sum(1 for s in state["active_subagents"] if s["status"] == "completing")
        completed_count = sum(1 for s in state["active_subagents"] if s["status"] == "completed")
        
        return {
            "total_tracked": len(state["active_subagents"]),
            "active": active_count,
            "completing": completing_count,
            "completed": completed_count,
            "last_updated": state.get("last_updated", 0)
        }


def test_tracker():
    """Test the active subagent tracker."""
    tracker = ActiveSubagentTracker()
    
    print("=== Testing Active Subagent Tracker ===\n")
    
    # Register some subagents
    print("1. Registering subagents...")
    id1 = tracker.register_start(
        session_id="test-session",
        subagent_type="sdk-architect",
        description="Design architecture",
        prompt="Design the SDK architecture...",
        task_line_number=100
    )
    print(f"   Registered sdk-architect with ID: {id1}")
    
    time.sleep(1)
    
    id2 = tracker.register_start(
        session_id="test-session",
        subagent_type="sdk-protocol-specialist",
        description="Analyze protocol",
        prompt="Analyze the protocol...",
        task_line_number=150
    )
    print(f"   Registered sdk-protocol-specialist with ID: {id2}")
    
    # Get active subagents
    print("\n2. Getting active subagents...")
    active = tracker.get_active_subagents("test-session")
    for subagent in active:
        print(f"   - {subagent.subagent_type} ({subagent.tracking_id}): {subagent.status}")
    
    # Simulate SubagentStop - find likely stopped
    print("\n3. Simulating SubagentStop...")
    hints = {
        "last_sidechain_type": "sdk-protocol-specialist",
        "last_sidechain_line": 160
    }
    
    likely_stopped = tracker.find_likely_stopped_subagent("test-session", hints)
    if likely_stopped:
        print(f"   Likely stopped: {likely_stopped.subagent_type} ({likely_stopped.tracking_id})")
        tracker.mark_completed(likely_stopped.tracking_id)
    
    # Check summary
    print("\n4. Tracking summary:")
    summary = tracker.get_tracking_summary()
    for key, value in summary.items():
        print(f"   {key}: {value}")
    
    # Cleanup
    print("\n5. Cleaning up test data...")
    if os.path.exists(tracker.state_file):
        os.remove(tracker.state_file)
    if os.path.exists(tracker.lock_file):
        os.remove(tracker.lock_file)
    print("   Cleanup complete")


if __name__ == "__main__":
    test_tracker()