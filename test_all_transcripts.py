#!/usr/bin/env python3
"""
Comprehensive test of enhanced parser on all transcripts to identify edge cases.
"""

import json
import time
import os
import sys
import traceback
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, 'template')
from enhanced_stats_analyzer import EnhancedStatsAnalyzer
from sidechain_reconstructor import SidechainReconstructor

def test_transcript(file_path: str) -> dict:
    """Test parsing a single transcript file and capture any issues."""
    result = {
        'file_path': file_path,
        'status': 'success',
        'messages': 0,
        'subagents': 0,
        'stats': {},
        'errors': [],
        'warnings': []
    }
    
    try:
        # Load messages
        with open(file_path, 'r') as f:
            lines = f.readlines()
        result['messages'] = len(lines)
        
        messages = []
        for i, line in enumerate(lines, 1):
            if line.strip():
                try:
                    msg = json.loads(line)
                    messages.append(msg)
                except json.JSONDecodeError as e:
                    result['errors'].append(f"Line {i}: JSON decode error - {e}")
        
        # Try sidechain reconstruction
        try:
            reconstructor = SidechainReconstructor(file_path)
            chains = reconstructor.reconstruct_all_subagent_chains()
            result['subagents'] = len(chains)
            
            # Analyze each subagent with enhanced stats
            analyzer = EnhancedStatsAnalyzer()
            for chain in chains:
                try:
                    stats = analyzer.analyze_conversation(chain['messages'])
                    # Check for unusual stats
                    if stats['total_runtime'] < 0:
                        result['warnings'].append(f"Negative runtime for {chain['subagent_type']}: {stats['total_runtime']}")
                    if stats['total_runtime'] > 86400:  # > 24 hours
                        result['warnings'].append(f"Very long runtime for {chain['subagent_type']}: {stats['total_runtime']/3600:.1f} hours")
                    if stats['total_turns'] == 0 and len(chain['messages']) > 2:
                        result['warnings'].append(f"No turns counted for {chain['subagent_type']} with {len(chain['messages'])} messages")
                except Exception as e:
                    result['errors'].append(f"Stats analysis error for {chain['subagent_type']}: {e}")
            
        except Exception as e:
            result['errors'].append(f"Sidechain reconstruction error: {e}")
        
        # Test direct stats analysis on main transcript
        try:
            analyzer = EnhancedStatsAnalyzer()
            main_stats = analyzer.analyze_conversation(messages)
            result['stats'] = main_stats
            
            # Edge case checks
            if main_stats['files_created'] > 1000:
                result['warnings'].append(f"Unusually high files created: {main_stats['files_created']}")
            if main_stats['files_deleted'] > main_stats['files_created']:
                result['warnings'].append(f"More files deleted ({main_stats['files_deleted']}) than created ({main_stats['files_created']})")
                
        except Exception as e:
            result['errors'].append(f"Main stats analysis error: {e}")
            
    except Exception as e:
        result['status'] = 'failed'
        result['errors'].append(f"Fatal error: {e}")
        result['traceback'] = traceback.format_exc()
    
    if result['errors']:
        result['status'] = 'error'
    elif result['warnings']:
        result['status'] = 'warning'
    
    return result

def test_all_projects(directory: str, limit: int = None) -> None:
    """Test all transcript files in the projects directory."""
    project_dirs = list(Path(directory).iterdir())
    if limit:
        project_dirs = project_dirs[:limit]
    
    results = {
        'success': [],
        'warning': [],
        'error': [],
        'failed': []
    }
    
    error_types = defaultdict(list)
    warning_types = defaultdict(list)
    total_files = 0
    total_messages = 0
    total_subagents = 0
    
    print(f"🔍 Testing enhanced parser on all transcripts in {directory}")
    print("=" * 80)
    
    for project_dir in project_dirs:
        if not project_dir.is_dir():
            continue
        
        # Find all transcript files
        transcripts = list(project_dir.glob("*.jsonl"))
        
        for transcript in transcripts:
            total_files += 1
            print(f"\n📁 Testing: {project_dir.name}/{transcript.name}")
            
            result = test_transcript(str(transcript))
            results[result['status']].append(result)
            total_messages += result['messages']
            total_subagents += result['subagents']
            
            # Print immediate feedback
            if result['status'] == 'success':
                print(f"   ✅ Success: {result['messages']} messages, {result['subagents']} subagents")
            elif result['status'] == 'warning':
                print(f"   ⚠️  Warning: {result['messages']} messages, {result['subagents']} subagents")
                for warning in result['warnings']:
                    print(f"      - {warning}")
                    # Categorize warning
                    if 'runtime' in warning.lower():
                        warning_types['runtime_issues'].append(result['file_path'])
                    elif 'turns' in warning.lower():
                        warning_types['turn_count_issues'].append(result['file_path'])
                    elif 'files' in warning.lower():
                        warning_types['file_operation_issues'].append(result['file_path'])
                    else:
                        warning_types['other'].append(result['file_path'])
            elif result['status'] == 'error':
                print(f"   ❌ Error: {result['messages']} messages, {result['subagents']} subagents")
                for error in result['errors']:
                    print(f"      - {error}")
                    # Categorize error
                    if 'JSON decode' in error:
                        error_types['json_decode'].append(result['file_path'])
                    elif 'Sidechain reconstruction' in error:
                        error_types['sidechain_reconstruction'].append(result['file_path'])
                    elif 'Stats analysis' in error:
                        error_types['stats_analysis'].append(result['file_path'])
                    elif 'KeyError' in error:
                        error_types['key_error'].append(result['file_path'])
                    elif 'TypeError' in error:
                        error_types['type_error'].append(result['file_path'])
                    else:
                        error_types['other'].append(result['file_path'])
            else:  # failed
                print(f"   💀 FATAL: {result.get('errors', ['Unknown error'])[0]}")
                if 'traceback' in result:
                    print(f"      Traceback: {result['traceback'][:200]}...")
    
    # Summary Report
    print("\n" + "=" * 80)
    print("📊 COMPREHENSIVE TEST SUMMARY")
    print("=" * 80)
    
    print(f"\n📈 Overall Statistics:")
    print(f"   • Files tested: {total_files}")
    print(f"   • Total messages: {total_messages:,}")
    print(f"   • Total subagents found: {total_subagents}")
    print(f"   • Average messages/file: {total_messages/total_files:.1f}" if total_files else "   • No files tested")
    
    print(f"\n📊 Results Distribution:")
    print(f"   • ✅ Success: {len(results['success'])} files ({len(results['success'])*100/total_files:.1f}%)" if total_files else "   • No files")
    print(f"   • ⚠️  Warnings: {len(results['warning'])} files ({len(results['warning'])*100/total_files:.1f}%)" if total_files else "")
    print(f"   • ❌ Errors: {len(results['error'])} files ({len(results['error'])*100/total_files:.1f}%)" if total_files else "")
    print(f"   • 💀 Failed: {len(results['failed'])} files ({len(results['failed'])*100/total_files:.1f}%)" if total_files else "")
    
    # Error Analysis
    if error_types:
        print(f"\n🔴 Error Categories:")
        for error_type, files in sorted(error_types.items(), key=lambda x: len(x[1]), reverse=True):
            print(f"   • {error_type}: {len(files)} occurrences")
            if len(files) <= 3:
                for f in files[:3]:
                    print(f"      - {Path(f).parent.name}/{Path(f).name}")
    
    # Warning Analysis
    if warning_types:
        print(f"\n⚠️  Warning Categories:")
        for warning_type, files in sorted(warning_types.items(), key=lambda x: len(x[1]), reverse=True):
            print(f"   • {warning_type}: {len(files)} occurrences")
            if len(files) <= 3:
                for f in files[:3]:
                    print(f"      - {Path(f).parent.name}/{Path(f).name}")
    
    # Edge Cases Found
    print(f"\n🎯 Edge Cases Identified:")
    edge_cases = []
    
    # Check for transcripts with no subagents but many messages
    for r in results['success'] + results['warning']:
        if r['subagents'] == 0 and r['messages'] > 100:
            edge_cases.append(f"Large transcript with no subagents: {Path(r['file_path']).parent.name} ({r['messages']} messages)")
    
    # Check for transcripts with many subagents
    for r in results['success'] + results['warning']:
        if r['subagents'] > 10:
            edge_cases.append(f"Many subagents: {Path(r['file_path']).parent.name} ({r['subagents']} subagents)")
    
    # Check for very small transcripts
    for r in results['success'] + results['warning']:
        if r['messages'] < 5:
            edge_cases.append(f"Very small transcript: {Path(r['file_path']).parent.name} ({r['messages']} messages)")
    
    if edge_cases:
        for i, case in enumerate(edge_cases[:10], 1):
            print(f"   {i}. {case}")
        if len(edge_cases) > 10:
            print(f"   ... and {len(edge_cases) - 10} more edge cases")
    else:
        print("   • No significant edge cases found")
    
    # Files with most issues
    if results['error'] or results['failed']:
        print(f"\n🔥 Files Requiring Attention:")
        problem_files = results['error'] + results['failed']
        for r in problem_files[:5]:
            print(f"   • {Path(r['file_path']).parent.name}/{Path(r['file_path']).name}")
            for error in r['errors'][:2]:
                print(f"      - {error[:100]}...")
    
    # Success stories
    if results['success']:
        largest_success = max(results['success'], key=lambda x: x['messages'])
        print(f"\n✨ Largest Successfully Processed:")
        print(f"   • {Path(largest_success['file_path']).parent.name}/{Path(largest_success['file_path']).name}")
        print(f"     - {largest_success['messages']} messages, {largest_success['subagents']} subagents")
        
        if largest_success['stats']:
            stats = largest_success['stats']
            print(f"     - Runtime: {stats.get('total_runtime', 0)/3600:.1f} hours")
            print(f"     - File operations: {stats.get('files_created', 0)} created, {stats.get('files_modified', 0)} modified")

if __name__ == "__main__":
    import sys
    
    directory = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.claude/projects")
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    
    test_all_projects(directory, limit)