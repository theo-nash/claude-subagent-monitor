#!/usr/bin/env python3
"""
Robust subagent stop detection combining multiple strategies.
Uses active tracking, transcript analysis, and heuristics.
"""

import os
import json
import time
from typing import Dict, Any, Optional, Tuple
from active_subagent_tracker import ActiveSubagentTracker, ActiveSubagent
from sidechain_reconstructor import SidechainReconstructor

class RobustSubagentDetector:
    """
    Combines multiple detection strategies to reliably identify which subagent stopped.
    
    Strategies:
    1. Active subagent tracking (primary)
    2. Transcript sidechain analysis (validation)
    3. Timing and pattern heuristics (fallback)
    """
    
    def __init__(self):
        self.tracker = ActiveSubagentTracker()
        
    def detect_stopped_subagent(self, hook_data: Dict[str, Any]) -> Tuple[Optional[str], float, Dict[str, Any]]:
        """
        Detect which subagent stopped when SubagentStop hook fires.
        
        Args:
            hook_data: Data from SubagentStop hook
        
        Returns:
            Tuple of (subagent_type, confidence_score, details)
            - subagent_type: Type of subagent that stopped (or None)
            - confidence_score: 0.0 to 1.0 confidence in detection
            - details: Additional information about the detection
        """
        session_id = hook_data.get('session_id')
        transcript_path = hook_data.get('transcript_path')
        
        details = {
            'detection_method': [],
            'active_candidates': 0,
            'transcript_hints': {},
            'selected_tracking_id': None
        }
        
        # Strategy 1: Check active subagent tracker
        active_subagents = self.tracker.get_active_subagents(session_id)
        details['active_candidates'] = len(active_subagents)
        
        if not active_subagents:
            # No active subagents tracked
            details['detection_method'].append('no_active_tracked')
            return None, 0.0, details
        
        # Strategy 2: Get hints from transcript if available
        transcript_hints = {}
        if transcript_path and os.path.exists(transcript_path):
            transcript_hints = self._analyze_transcript_for_hints(transcript_path)
            details['transcript_hints'] = transcript_hints
        
        # Strategy 3: Use tracker's intelligent selection
        likely_stopped = self.tracker.find_likely_stopped_subagent(
            session_id, 
            transcript_hints
        )
        
        if not likely_stopped:
            details['detection_method'].append('no_match_found')
            return None, 0.0, details
        
        # Calculate confidence score
        confidence = self._calculate_confidence(
            likely_stopped, 
            active_subagents, 
            transcript_hints
        )
        
        details['selected_tracking_id'] = likely_stopped.tracking_id
        details['detection_method'].append('active_tracker')
        if transcript_hints:
            details['detection_method'].append('transcript_validated')
        
        # Mark as completing/completed
        self.tracker.mark_completing(likely_stopped.tracking_id)
        
        return likely_stopped.subagent_type, confidence, details
    
    def _analyze_transcript_for_hints(self, transcript_path: str) -> Dict[str, Any]:
        """
        Analyze transcript to get hints about which subagent stopped.
        
        Returns dict with:
        - last_sidechain_type: Type of last active sidechain
        - last_sidechain_line: Line number of last sidechain message
        - has_completion_pattern: Whether completion patterns found
        """
        hints = {}
        
        try:
            # Quick scan of last few lines for sidechain activity
            with open(transcript_path, 'r') as f:
                lines = f.readlines()
            
            # Check last 20 lines for sidechain messages
            for i in range(len(lines) - 1, max(0, len(lines) - 20) - 1, -1):
                try:
                    entry = json.loads(lines[i])
                    
                    if entry.get('isSidechain'):
                        # Found a sidechain message
                        hints['last_sidechain_line'] = i + 1
                        
                        # Try to identify subagent type from chain reconstruction
                        reconstructor = SidechainReconstructor(transcript_path)
                        reconstructor.load_transcript()
                        chains = reconstructor.reconstruct_all_subagent_chains()
                        
                        # Find which chain contains this message
                        entry_uuid = entry.get('uuid')
                        for chain_info in chains:
                            for msg in chain_info['messages']:
                                if msg.get('uuid') == entry_uuid:
                                    hints['last_sidechain_type'] = chain_info['subagent_type']
                                    break
                            if 'last_sidechain_type' in hints:
                                break
                        
                        # Check for completion patterns
                        msg_content = str(entry.get('message', {}).get('content', '')).lower()
                        completion_patterns = [
                            'task complete', 'finished', 'returning to main',
                            'completed successfully', 'done', 'task accomplished'
                        ]
                        
                        if any(pattern in msg_content for pattern in completion_patterns):
                            hints['has_completion_pattern'] = True
                        
                        break  # Stop after finding first sidechain message
                        
                except (json.JSONDecodeError, KeyError):
                    continue
                    
        except Exception as e:
            print(f"Error analyzing transcript: {e}")
        
        return hints
    
    def _calculate_confidence(self, selected: ActiveSubagent, 
                            all_active: list, 
                            transcript_hints: Dict) -> float:
        """
        Calculate confidence score for the detection.
        
        Score factors:
        - 1.0 if only one active subagent
        - 0.9 if transcript type matches selected
        - 0.7 if multiple active but clear winner
        - 0.5 if multiple active and uncertain
        """
        if len(all_active) == 1:
            return 1.0
        
        confidence = 0.5  # Base confidence with multiple active
        
        # Boost if transcript confirms
        if transcript_hints.get('last_sidechain_type') == selected.subagent_type:
            confidence += 0.3
        
        # Boost if completion pattern found
        if transcript_hints.get('has_completion_pattern'):
            confidence += 0.1
        
        # Boost if recently started (likely to complete)
        age = int(time.time()) - selected.start_timestamp
        if age < 30:  # Less than 30 seconds old
            confidence += 0.1
        
        return min(confidence, 0.95)  # Cap at 0.95 for multiple active


def test_detection():
    """Test the robust detection system."""
    print("=== Testing Robust Subagent Detection ===\n")
    
    detector = RobustSubagentDetector()
    
    # Set up test scenario
    print("1. Setting up test scenario...")
    
    # Register some active subagents
    tracker = detector.tracker
    
    id1 = tracker.register_start(
        session_id="test-session",
        subagent_type="sdk-architect",
        description="Design architecture",
        prompt="Design the SDK...",
        task_line_number=100
    )
    print(f"   Registered sdk-architect: {id1}")
    
    time.sleep(0.5)
    
    id2 = tracker.register_start(
        session_id="test-session",
        subagent_type="sdk-protocol-specialist",
        description="Analyze protocol",
        prompt="Analyze the protocol...",
        task_line_number=150
    )
    print(f"   Registered sdk-protocol-specialist: {id2}")
    
    # Simulate SubagentStop hook
    print("\n2. Simulating SubagentStop hook...")
    
    hook_data = {
        'session_id': 'test-session',
        'transcript_path': '/path/to/transcript.jsonl'  # Won't exist in test
    }
    
    subagent_type, confidence, details = detector.detect_stopped_subagent(hook_data)
    
    print(f"\n3. Detection Results:")
    print(f"   Detected: {subagent_type}")
    print(f"   Confidence: {confidence:.2f}")
    print(f"   Method: {', '.join(details['detection_method'])}")
    print(f"   Active candidates: {details['active_candidates']}")
    print(f"   Selected ID: {details['selected_tracking_id']}")
    
    # Test with real transcript
    print("\n4. Testing with real transcript...")
    # Example usage - replace with your actual transcript path
    real_transcript = '~/.claude/projects/YOUR_PROJECT/YOUR_SESSION_ID.jsonl'
    
    if os.path.exists(real_transcript):
        hook_data['transcript_path'] = real_transcript
        
        # Register a matching subagent
        id3 = tracker.register_start(
            session_id="test-session",
            subagent_type="sdk-architect",  # Matches last in transcript
            description="Update memories",
            prompt="Update your memories...",
            task_line_number=300
        )
        
        subagent_type, confidence, details = detector.detect_stopped_subagent(hook_data)
        
        print(f"   Detected: {subagent_type}")
        print(f"   Confidence: {confidence:.2f}")
        print(f"   Transcript hints: {details['transcript_hints']}")
    
    # Cleanup
    print("\n5. Cleaning up...")
    if os.path.exists(tracker.state_file):
        os.remove(tracker.state_file)
    if os.path.exists(tracker.lock_file):
        os.remove(tracker.lock_file)
    print("   Cleanup complete")
    
    print("\n=== Summary ===")
    print("The robust detector combines:")
    print("1. Active subagent tracking (persistent state)")
    print("2. Transcript analysis for validation")
    print("3. Intelligent scoring and selection")
    print("4. Confidence scoring for reliability")


if __name__ == "__main__":
    test_detection()