#!/usr/bin/env python3
"""
Sidechain reconstructor for Claude Code subagent conversations.
Rebuilds complete subagent conversation chains using UUID linking and prompt matching.
"""

import json
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime
from collections import defaultdict

class SidechainReconstructor:
    def __init__(self, transcript_path: str):
        self.transcript_path = transcript_path
        self.entries = []
        self.uuid_map = {}
        self.sidechain_roots = []
        self.task_invocations = []
        self.subagent_chains = []
        
    def load_transcript(self) -> bool:
        """Load and index all transcript entries."""
        try:
            with open(self.transcript_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            for line_num, line in enumerate(lines):
                try:
                    entry = json.loads(line)
                    entry['_line_number'] = line_num + 1
                    
                    # Convert timestamp to Unix timestamp
                    timestamp_str = entry.get('timestamp', '')
                    if timestamp_str:
                        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        entry['_timestamp'] = int(dt.timestamp() * 1000)  # milliseconds
                    else:
                        entry['_timestamp'] = 0
                    
                    self.entries.append(entry)
                    
                    # Index by UUID
                    if 'uuid' in entry:
                        self.uuid_map[entry['uuid']] = entry
                        
                except json.JSONDecodeError:
                    continue
                    
            print(f"Loaded {len(self.entries)} entries from transcript")
            return True
            
        except Exception as e:
            print(f"Error loading transcript: {e}")
            return False
    
    def identify_sidechain_roots(self):
        """Find all sidechain messages with no parent (roots of chains)."""
        for entry in self.entries:
            if entry.get('isSidechain', False):
                parent_uuid = entry.get('parentUuid')
                if not parent_uuid or parent_uuid == 'null':
                    self.sidechain_roots.append(entry)
                    print(f"Found sidechain root at line {entry['_line_number']}: {entry.get('uuid', 'no-uuid')[:8]}...")
        
        print(f"Found {len(self.sidechain_roots)} sidechain roots")
        return self.sidechain_roots
    
    def identify_task_invocations(self):
        """Find all Task tool invocations in the main chain."""
        for entry in self.entries:
            if not entry.get('isSidechain', False):
                msg = entry.get('message', {})
                if msg.get('role') == 'assistant':
                    content = msg.get('content', [])
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and item.get('type') == 'tool_use' and item.get('name') == 'Task':
                                task_info = {
                                    'entry': entry,
                                    'line_number': entry['_line_number'],
                                    'timestamp': entry['_timestamp'],
                                    'input': item.get('input', {}),
                                    'subagent_type': item.get('input', {}).get('subagent_type', 'unknown'),
                                    'prompt': item.get('input', {}).get('prompt', ''),
                                    'description': item.get('input', {}).get('description', '')
                                }
                                self.task_invocations.append(task_info)
                                print(f"Found Task invocation at line {entry['_line_number']}: {task_info['subagent_type']}")
        
        print(f"Found {len(self.task_invocations)} Task invocations")
        return self.task_invocations
    
    def trace_chain_backward(self, start_entry: Dict) -> List[Dict]:
        """Trace a sidechain backward from any entry to its root."""
        chain = [start_entry]
        current = start_entry
        visited = {start_entry['uuid']}
        
        while True:
            parent_uuid = current.get('parentUuid')
            if not parent_uuid or parent_uuid == 'null':
                # Reached the root
                break
                
            if parent_uuid in visited:
                # Circular reference protection
                print(f"Warning: Circular reference detected at {parent_uuid}")
                break
                
            if parent_uuid not in self.uuid_map:
                # Parent not found - broken chain
                print(f"Warning: Parent {parent_uuid} not found for {current['uuid']}")
                break
                
            parent = self.uuid_map[parent_uuid]
            chain.insert(0, parent)  # Add to beginning to maintain order
            visited.add(parent_uuid)
            current = parent
            
        return chain
    
    def find_chain_from_root(self, root_entry: Dict) -> List[Dict]:
        """Build forward chain starting from a root entry."""
        chain = [root_entry]
        children_map = defaultdict(list)
        
        # Build parent->children map
        for entry in self.entries:
            if entry.get('isSidechain', False):
                parent_uuid = entry.get('parentUuid')
                if parent_uuid and parent_uuid != 'null':
                    children_map[parent_uuid].append(entry)
        
        # Trace forward from root
        to_process = [root_entry]
        visited = {root_entry['uuid']}
        
        while to_process:
            current = to_process.pop(0)
            current_uuid = current.get('uuid')
            
            if current_uuid in children_map:
                children = sorted(children_map[current_uuid], key=lambda x: x['_timestamp'])
                for child in children:
                    if child['uuid'] not in visited:
                        chain.append(child)
                        to_process.append(child)
                        visited.add(child['uuid'])
        
        return chain
    
    def match_prompt_to_task(self, sidechain_root: Dict, task_invocations: List[Dict]) -> Optional[Dict]:
        """Match a sidechain root to its initiating Task invocation by prompt."""
        # Get the prompt from the sidechain root message
        root_msg = sidechain_root.get('message', {})
        root_content = root_msg.get('content', '')
        
        # Convert to string if it's a list
        if isinstance(root_content, list):
            root_content = ' '.join(str(item) for item in root_content)
        else:
            root_content = str(root_content)
        
        # Look for Task invocations that came before this sidechain
        root_timestamp = sidechain_root['_timestamp']
        
        # Find the most recent Task invocation before this sidechain that matches
        best_match = None
        for task in task_invocations:
            if task['timestamp'] < root_timestamp:
                task_prompt = task['prompt']
                
                # Check for exact prompt match or significant overlap
                if task_prompt and (task_prompt in root_content or root_content in task_prompt):
                    if not best_match or task['timestamp'] > best_match['timestamp']:
                        best_match = task
        
        return best_match
    
    def reconstruct_all_subagent_chains(self) -> List[Dict]:
        """Reconstruct all subagent conversation chains."""
        # Load and index everything
        if not self.entries:
            self.load_transcript()
        
        # Find all components
        self.identify_sidechain_roots()
        self.identify_task_invocations()
        
        # Match each sidechain root to its Task invocation
        for root in self.sidechain_roots:
            task = self.match_prompt_to_task(root, self.task_invocations)
            
            if task:
                # Build the complete chain
                chain = self.find_chain_from_root(root)
                
                subagent_info = {
                    'subagent_type': task['subagent_type'],
                    'description': task['description'],
                    'task_line': task['line_number'],
                    'task_timestamp': task['timestamp'],
                    'root_line': root['_line_number'],
                    'root_uuid': root['uuid'],
                    'chain_length': len(chain),
                    'messages': chain,
                    'task_entry': task['entry']
                }
                
                self.subagent_chains.append(subagent_info)
                print(f"Matched chain: {task['subagent_type']} - {len(chain)} messages")
            else:
                print(f"Warning: Could not match sidechain root at line {root['_line_number']} to any Task")
        
        return self.subagent_chains
    
    def get_subagent_conversation(self, subagent_type: str) -> Optional[List[Dict]]:
        """Get the conversation chain for a specific subagent type."""
        for chain_info in self.subagent_chains:
            if chain_info['subagent_type'] == subagent_type:
                return chain_info['messages']
        return None
    
    def analyze_subagent_chains(self) -> Dict:
        """Analyze all reconstructed chains for statistics."""
        stats = {
            'total_chains': len(self.subagent_chains),
            'subagent_types': {},
            'chain_lengths': [],
            'total_sidechain_messages': 0
        }
        
        for chain_info in self.subagent_chains:
            subagent_type = chain_info['subagent_type']
            chain_length = chain_info['chain_length']
            
            if subagent_type not in stats['subagent_types']:
                stats['subagent_types'][subagent_type] = {
                    'count': 0,
                    'total_messages': 0,
                    'chains': []
                }
            
            stats['subagent_types'][subagent_type]['count'] += 1
            stats['subagent_types'][subagent_type]['total_messages'] += chain_length
            stats['subagent_types'][subagent_type]['chains'].append({
                'task_line': chain_info['task_line'],
                'length': chain_length,
                'description': chain_info['description']
            })
            
            stats['chain_lengths'].append(chain_length)
            stats['total_sidechain_messages'] += chain_length
        
        if stats['chain_lengths']:
            stats['avg_chain_length'] = sum(stats['chain_lengths']) / len(stats['chain_lengths'])
            stats['max_chain_length'] = max(stats['chain_lengths'])
            stats['min_chain_length'] = min(stats['chain_lengths'])
        
        return stats


def test_reconstruction():
    """Test the sidechain reconstruction with a real transcript."""
    # Example usage - replace with your actual transcript path
    transcript_path = '~/.claude/projects/YOUR_PROJECT/YOUR_SESSION_ID.jsonl'
    
    print("=== Testing Sidechain Reconstruction ===\n")
    
    reconstructor = SidechainReconstructor(transcript_path)
    
    # Load and reconstruct
    print("1. Loading transcript...")
    reconstructor.load_transcript()
    
    print("\n2. Reconstructing subagent chains...")
    chains = reconstructor.reconstruct_all_subagent_chains()
    
    print(f"\n3. Reconstruction complete:")
    print(f"   - Found {len(chains)} complete subagent chains")
    
    # Analyze results
    print("\n4. Chain Analysis:")
    stats = reconstructor.analyze_subagent_chains()
    
    for subagent_type, info in stats['subagent_types'].items():
        print(f"\n   {subagent_type}:")
        print(f"   - Invocations: {info['count']}")
        print(f"   - Total messages: {info['total_messages']}")
        print(f"   - Average messages per invocation: {info['total_messages'] / info['count']:.1f}")
        
        for i, chain in enumerate(info['chains'], 1):
            print(f"     Chain {i}: {chain['length']} messages (line {chain['task_line']})")
            print(f"       Description: {chain['description'][:50]}...")
    
    print(f"\n5. Overall Statistics:")
    print(f"   - Total chains: {stats['total_chains']}")
    print(f"   - Total sidechain messages: {stats['total_sidechain_messages']}")
    if stats.get('avg_chain_length'):
        print(f"   - Average chain length: {stats['avg_chain_length']:.1f}")
        print(f"   - Min chain length: {stats['min_chain_length']}")
        print(f"   - Max chain length: {stats['max_chain_length']}")
    
    # Test extracting a specific chain
    if chains:
        first_chain = chains[0]
        print(f"\n6. Sample Chain Details:")
        print(f"   Subagent: {first_chain['subagent_type']}")
        print(f"   Task at line: {first_chain['task_line']}")
        print(f"   Chain starts at line: {first_chain['root_line']}")
        print(f"   Messages in chain: {first_chain['chain_length']}")
        
        # Show first few messages
        print(f"\n   First 3 messages in chain:")
        for i, msg in enumerate(first_chain['messages'][:3], 1):
            role = msg.get('message', {}).get('role', 'unknown')
            line = msg.get('_line_number', '?')
            print(f"   {i}. Line {line}: Role={role}")
            
            # Show content preview
            content = msg.get('message', {}).get('content', '')
            if isinstance(content, list) and content:
                content_preview = str(content[0])[:100]
            else:
                content_preview = str(content)[:100]
            print(f"      Content: {content_preview}...")


if __name__ == "__main__":
    test_reconstruction()