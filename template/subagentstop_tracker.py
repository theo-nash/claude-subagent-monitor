#!/usr/bin/env python3
"""
Enhanced SubagentStop hook for Claude Code subagent tracking.
Uses robust detection to identify which subagent stopped.
"""

import sys
import os
from typing import Dict, Any

from database_utils import SubagentTracker, read_hook_input, write_hook_response, log_debug
from robust_subagent_detector import RobustSubagentDetector
from transcript_parser import TranscriptParser, parse_latest_subagent_conversation
from enhanced_stats_analyzer import EnhancedStatsAnalyzer

def main():
    """Main hook execution function."""
    try:
        # Read hook input from Claude Code
        hook_data = read_hook_input()
        
        if not hook_data:
            log_debug("No hook data received")
            write_hook_response(exit_code=0)
            return
        
        session_id = hook_data.get('session_id')
        transcript_path = hook_data.get('transcript_path')
        
        log_debug(f"SubagentStop hook triggered", {
            'session_id': session_id,
            'transcript_path': transcript_path
        })
        
        # Use robust detector to identify which subagent stopped
        detector = RobustSubagentDetector()
        subagent_type, confidence, detection_details = detector.detect_stopped_subagent(hook_data)
        
        if not subagent_type:
            log_debug("Could not determine which subagent stopped", detection_details)
            write_hook_response(exit_code=0)
            return
        
        log_debug(f"Detected stopped subagent", {
            'subagent_type': subagent_type,
            'confidence': confidence,
            'method': detection_details.get('detection_method', []),
            'tracking_id': detection_details.get('selected_tracking_id')
        })
        
        # Determine success status based on confidence and detection
        if confidence >= 0.8:
            success_status = 'completed'
        elif confidence >= 0.5:
            success_status = 'likely_completed'
        else:
            success_status = 'uncertain'
        
        # Initialize database tracker
        db_tracker = SubagentTracker()
        
        # Mark subagent as stopped in database
        subagent_session_id = db_tracker.stop_subagent(
            session_id=session_id,
            subagent_type=subagent_type,
            success_status=success_status
        )
        
        if not subagent_session_id:
            log_debug(f"No active database record found for subagent", {
                'session_id': session_id,
                'subagent_type': subagent_type
            })
            # Continue anyway - we still have useful data
        else:
            log_debug(f"Marked subagent as stopped in database", {
                'subagent_session_id': subagent_session_id,
                'subagent_type': subagent_type,
                'success_status': success_status
            })
        
        # Parse transcript for detailed statistics if available
        stats_updated = False
        enhanced_stats = None
        if transcript_path and os.path.exists(transcript_path) and subagent_session_id:
            try:
                # Use enhanced parser to get latest conversation stats
                tool_usage, message_stats, token_estimate = parse_latest_subagent_conversation(
                    transcript_path, subagent_type
                )
                
                # Get the actual conversation for enhanced analysis
                parser = TranscriptParserV2(transcript_path)
                conversation = parser.get_latest_subagent_conversation(subagent_type)
                
                # Analyze with enhanced stats analyzer
                if conversation:
                    analyzer = EnhancedStatsAnalyzer()
                    enhanced_stats = analyzer.analyze_conversation(conversation)
                    
                    log_debug(f"Enhanced statistics collected", {
                        'runtime': enhanced_stats.get('total_runtime'),
                        'turns': enhanced_stats.get('total_turns'),
                        'files_created': enhanced_stats.get('files_created'),
                        'files_modified': enhanced_stats.get('files_modified'),
                        'docs_updated': enhanced_stats.get('documentation_updated')
                    })
                
                if tool_usage or message_stats or enhanced_stats:
                    # Update database with all statistics
                    db_tracker.update_statistics(
                        subagent_session_id=subagent_session_id,
                        tool_stats=tool_usage,
                        message_stats=message_stats,
                        total_tokens=token_estimate,
                        enhanced_stats=enhanced_stats
                    )
                    
                    stats_updated = True
                    
                    log_debug(f"Updated subagent statistics from transcript", {
                        'subagent_session_id': subagent_session_id,
                        'tools_used': len(tool_usage) if tool_usage else 0,
                        'total_tool_calls': sum(tool_usage.values()) if tool_usage else 0,
                        'message_types': len(message_stats) if message_stats else 0,
                        'estimated_tokens': token_estimate,
                        'enhanced_metrics': bool(enhanced_stats)
                    })
                
            except Exception as e:
                log_debug(f"Error parsing transcript for statistics: {e}")
                if subagent_session_id:
                    db_tracker.log_error(
                        subagent_session_id=subagent_session_id,
                        error_type='transcript_parse_error',
                        error_message=str(e)
                    )
        
        # Mark as completed in active tracker
        if detection_details.get('selected_tracking_id'):
            try:
                from active_subagent_tracker import ActiveSubagentTracker
                active_tracker = ActiveSubagentTracker()
                active_tracker.mark_completed(detection_details['selected_tracking_id'])
                log_debug(f"Marked tracking ID as completed", {
                    'tracking_id': detection_details['selected_tracking_id']
                })
            except Exception as e:
                log_debug(f"Error updating active tracker: {e}")
        
        # Build response message
        status_emoji = "✅" if confidence >= 0.8 else "⚠️" if confidence >= 0.5 else "❓"
        stats_info = ""
        
        if stats_updated:
            parts = []
            if enhanced_stats:
                if enhanced_stats.get('total_runtime'):
                    parts.append(f"{enhanced_stats['total_runtime']}s")
                if enhanced_stats.get('files_created') or enhanced_stats.get('files_modified'):
                    file_ops = []
                    if enhanced_stats.get('files_created'):
                        file_ops.append(f"{enhanced_stats['files_created']} created")
                    if enhanced_stats.get('files_modified'):
                        file_ops.append(f"{enhanced_stats['files_modified']} modified")
                    parts.append(f"files: {', '.join(file_ops)}")
            if tool_usage:
                tools_count = len(tool_usage)
                total_calls = sum(tool_usage.values())
                parts.append(f"{tools_count} tools")
            if parts:
                stats_info = f" - {', '.join(parts)}"
        
        response = {
            "continue": True,
            "message": f"{status_emoji} Subagent '{subagent_type}' stopped (confidence: {confidence:.0%}){stats_info}"
        }
        
        write_hook_response(response, exit_code=0)
        
    except Exception as e:
        log_debug(f"SubagentStop hook error: {e}")
        # Don't block on hook errors
        write_hook_response(exit_code=0)

if __name__ == "__main__":
    main()