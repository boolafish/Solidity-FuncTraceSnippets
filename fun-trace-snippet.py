from slither import Slither
from pathlib import Path
import json
import argparse
import sys
from typing import Optional, Dict, List, Set
from dataclasses import dataclass
from collections import defaultdict

@dataclass
class FunctionNode:
    name: str
    contract_name: str
    signature: str
    file: str
    definition: str
    calls: List[str]  # Keep as ordered list
    called_by: Set[str]
    source_lines: Optional[List[int]] = None  # Add source line info

class CallGraph:
    def __init__(self):
        self.nodes: Dict[str, FunctionNode] = {}  # Key will be "ContractName.functionSignature"
        self.edges: Dict[str, Set[str]] = defaultdict(set)
        self.reverse_edges: Dict[str, Set[str]] = defaultdict(set)

    def get_node_id(self, contract_name: str, func_signature: str, start: int) -> str:
        # Ignore start parameter, just use contract and signature
        return f"{contract_name}.{func_signature}"

    def add_node(self, name: str, contract_name: str, signature: str, start: int, length: int, file: str, definition: str, source_line: int):
        node_id = self.get_node_id(contract_name, signature, start)
        self.nodes[node_id] = FunctionNode(
            name=name,
            contract_name=contract_name,
            signature=signature,
            file=file,
            definition=definition,
            calls=[],
            called_by=set(),
            source_lines=[source_line]
        )

    def add_edge(self, caller_id: str, callee_id: str):
        """Simplified add_edge that just takes the node IDs directly"""
        self.edges[caller_id].add(callee_id)
        self.reverse_edges[callee_id].add(caller_id)

        if caller_id in self.nodes:
            self.nodes[caller_id].calls.append(callee_id)
        if callee_id in self.nodes:
            self.nodes[callee_id].called_by.add(caller_id)

def get_function_definition(func):
    """Helper function to get function definition from source"""
    try:
        if hasattr(func, 'source_mapping') and func.source_mapping and hasattr(func.source_mapping, 'filename'):
            with open(func.source_mapping.filename.absolute, 'r') as f:
                source = f.read()
                start = func.source_mapping.start
                length = func.source_mapping.length

                # Get the actual implementation, not just the interface
                if start + length <= len(source):
                    definition = source[start:start + length].strip()
                    # Check if this is just an interface definition
                    if definition.endswith(';'):
                        # Try to find the actual implementation
                        impl_start = source.find(f"function {func.name}")
                        if impl_start != -1:
                            # Find the matching closing brace
                            brace_count = 0
                            impl_end = impl_start
                            in_function = False
                            for i in range(impl_start, len(source)):
                                if source[i] == '{':
                                    brace_count += 1
                                    in_function = True
                                elif source[i] == '}':
                                    brace_count -= 1
                                    if in_function and brace_count == 0:
                                        impl_end = i + 1
                                        break
                            if impl_end > impl_start:
                                definition = source[impl_start:impl_end].strip()
                    return definition
    except Exception as e:
        print(f"Warning: Could not get definition for {func.name}: {str(e)}")
    return None

def get_function_signature(func) -> str:
    """Helper function to get full function signature"""
    try:
        # Get parameters
        params = []
        if hasattr(func, 'parameters'):
            for param in func.parameters:
                param_type = param.type
                param_name = param.name
                params.append(f"{param_type} {param_name}")

        # Get return values
        returns = []
        if hasattr(func, 'returns'):
            for ret in func.returns:
                ret_type = ret.type
                ret_name = ret.name
                returns.append(f"{ret_type}{f' {ret_name}' if ret_name else ''}")

        # Construct full signature
        signature = f"{func.name}({', '.join(params)})"
        if returns:
            signature += f" returns ({', '.join(returns)})"

        return signature
    except Exception as e:
        print(f"Warning: Could not get full signature for {func.name}: {str(e)}")
        return func.name

def get_call_line(call_info):
    call_type, (contract, function_call, call_expression) = call_info

    # 1. First try to get line from the call expression itself
    if call_expression and hasattr(call_expression, 'source_mapping'):
        if hasattr(call_expression.source_mapping, 'lines'):
            lines = call_expression.source_mapping.lines
            if lines:
                return lines[0]

    # 2. Try to get line from the expression property of function_call
    if hasattr(function_call, 'expression'):
        expr = function_call.expression
        if hasattr(expr, 'source_mapping') and hasattr(expr.source_mapping, 'lines'):
            lines = expr.source_mapping.lines
            if lines:
                return lines[0]

    # 3. Look for references to find actual call sites
    if hasattr(function_call, 'references'):
        for ref in function_call.references:
            if hasattr(ref, 'source_mapping') and hasattr(ref.source_mapping, 'lines'):
                lines = ref.source_mapping.lines
                if lines:
                    return lines[0]

    # 4. Try direct source mapping on function_call as last resort
    if hasattr(function_call, 'source_mapping'):
        if hasattr(function_call.source_mapping, 'lines'):
            lines = function_call.source_mapping.lines
            if lines:
                return lines[0]

    # 5. Add debug information
    print(f"Warning: Could not determine line number for {function_call.name}")
    print(f"Call type: {call_type}")
    print(f"Call expression available: {call_expression is not None}")
    if call_expression:
        print(f"Call expression attributes: {dir(call_expression)}")

    return float('inf')  # Return infinity for unknown line numbers

def extract_line_number(node):
    """Helper function to extract line number from a node"""
    if hasattr(node, 'source_mapping'):
        mapping = node.source_mapping
        if hasattr(mapping, 'lines') and mapping.lines:
            return mapping.lines[0]
        if hasattr(mapping, 'line') and mapping.line:
            return mapping.line
    return None

def get_call_line_from_snippet(function_body: str, function_name: str) -> int:
    """Get the line number where a function is called within a code snippet"""
    lines = function_body.split('\n')
    for i, line in enumerate(lines):
        if (f"{function_name}(" in line or f".{function_name}(" in line):
            return i + 1
    return float('inf')

def sort_calls_from_snippet(code_snippet: str, calls: list) -> list:
    """Sort function calls based on their appearance in the code snippet"""
    start = code_snippet.find('{')
    end = code_snippet.rfind('}')
    if start == -1 or end == -1:
        return calls

    function_body = code_snippet[start+1:end]
    call_lines = {
        call[1][1].name: get_call_line_from_snippet(function_body, call[1][1].name)
        for call in calls
    }

    return sorted(calls, key=lambda x: call_lines.get(x[1][1].name, float('inf')))

def collect_calls(func, contract, graph: CallGraph, visited=None, depth=0):
    """Recursively collect calls and build call graph."""
    if visited is None:
        visited = set()

    if (func.name.startswith('revert') or
        func.name in {'require', 'assert', 'abi.encode', 'abi.decode', 'abi.encodeCall',
                     'abi.encodePacked', 'encodePacked', 'encode', 'decode',
                     'keccak256'}):
        return

    contract_name = contract.name if contract else (
        func.contract.name if hasattr(func, 'contract') else "Unknown"
    )

    func_signature = get_function_signature(func)
    node_id = graph.get_node_id(contract_name, func_signature, 0)

    if node_id in visited:
        return
    visited.add(node_id)

    # When creating the node, store source line info
    if hasattr(func, 'source_mapping') and func.source_mapping:
        source_lines = func.source_mapping.lines if hasattr(func.source_mapping, 'lines') else []
        start_line = source_lines[0] if source_lines else 0
    else:
        start_line = 0

    # Add node to graph
    if hasattr(func, 'source_mapping'):
        try:
            definition = get_function_definition(func)
            graph.add_node(
                name=func.name,
                contract_name=contract_name,
                signature=func_signature,
                start=0,
                length=0,
                file=func.source_mapping.filename.absolute if func.source_mapping else "",
                definition=definition or "",
                source_line=start_line
            )
        except Exception as e:
            pass

    # Process calls in source order
    ordered_calls = []
    if hasattr(func, 'high_level_calls'):
        for call in func.high_level_calls:
            if isinstance(call, tuple):
                # Store the expression (call site) information
                call_expression, called_function = call
                ordered_calls.append(('high_level', (None, called_function, call_expression)))
            else:
                ordered_calls.append(('high_level', (None, call, None)))

    if hasattr(func, 'internal_calls'):
        for call in func.internal_calls:
            if hasattr(call, 'name'):
                # For internal calls, we need to find the call expression
                call_expression = next((expr for expr in func.expressions if
                    hasattr(expr, 'called') and expr.called == call), None)
                ordered_calls.append(('internal', (func.contract, call, call_expression)))

    # Get the function's source code if available
    source_code = None
    if hasattr(func, 'source_mapping') and func.source_mapping:
        try:
            filename = func.source_mapping.filename
            if filename and hasattr(filename, 'absolute'):
                with open(filename.absolute, 'r') as f:
                    source = f.read()
                    start = func.source_mapping.start
                    length = func.source_mapping.length
                    source_code = source[start:start + length]
        except Exception:
            pass

    if not source_code and hasattr(func, 'contract'):
        try:
            contract_path = func.contract.source_mapping.filename.absolute
            source_code = get_contract_source(contract_path, func.name)
        except Exception:
            pass

    # Sort the calls without debug prints
    if source_code:
        ordered_calls = sort_calls_from_snippet(source_code, ordered_calls)
    else:
        ordered_calls.sort(key=get_call_line)

    # Process calls in order
    for call_type, (contract_call, function_call, _) in ordered_calls:
        if not hasattr(function_call, 'name'):
            continue

        # Skip built-ins
        if (function_call.name.startswith('revert') or
            function_call.name in {'require', 'assert', 'abi.encode', 'abi.decode', 'abi.encodeCall',
                                 'abi.encodePacked', 'encodePacked', 'encode', 'decode',
                                 'keccak256'}):
            continue

        called_contract = contract_call or (
            function_call.contract if hasattr(function_call, 'contract') else None
        )
        called_contract_name = called_contract.name if called_contract else "Unknown"
        called_signature = get_function_signature(function_call)
        callee_id = graph.get_node_id(called_contract_name, called_signature, 0)

        graph.add_edge(node_id, callee_id)
        collect_calls(function_call, called_contract, graph, visited, depth + 1)

def print_execution_order(graph: CallGraph, root_function: str):
    """Print functions in execution order with hierarchical structure."""
    visited = set()

    def print_function_with_calls(node_id: str, depth: int = 0):
        if node_id in visited:
            return
        visited.add(node_id)

        node = graph.nodes.get(node_id)
        if not node:
            return

        indent = "    " * depth
        arrow = "-> " if depth > 0 else ""

        # Print current function
        print(f"{indent}{arrow}{node.contract_name}.{node.signature}")

        # Print details
        detail_indent = "    " * (depth + 1)
        if node.file:
            print(f"{detail_indent}File: {node.file}")
        if node.definition:
            print(f"{detail_indent}Code snippet:")
            print(f"{detail_indent}" + "-" * 40)
            for line in node.definition.split('\n'):
                print(f"{detail_indent}{line}")
            print(f"{detail_indent}" + "-" * 40)
        print()

        # Process calls in order they appear in the source
        for callee_id in node.calls:
            print_function_with_calls(callee_id, depth + 1)

    # Find root node
    root_id = None
    for node_id, node in graph.nodes.items():
        if node.name == root_function:
            root_id = node_id
            break

    if root_id:
        print("\nFunction call hierarchy:")
        print("=====================")
        print_function_with_calls(root_id)
    else:
        print(f"Function {root_function} not found in graph")

def list_contracts(file_path: str):
    """List all contracts in the given Solidity file"""
    try:
        slither = Slither(file_path)
        print("\nAvailable contracts:")
        for contract in slither.contracts:
            print(f"- {contract.name}")
    except Exception as e:
        print(f"Error loading contracts: {str(e)}")
        sys.exit(1)

def list_functions(file_path: str, contract_name: str):
    """List all functions in the given contract"""
    try:
        slither = Slither(file_path)
        contract = next((c for c in slither.contracts if c.name == contract_name), None)
        if contract is None:
            print(f"Contract {contract_name} not found")
            sys.exit(1)

        print(f"\nAvailable functions in {contract_name}:")
        for func in contract.functions:
            print(f"- {func.name}() - {func.visibility}")
    except Exception as e:
        print(f"Error loading functions: {str(e)}")
        sys.exit(1)

def analyze_function(file_path: str, contract_name: str, function_name: str):
    """Analyze a specific function in a contract"""
    try:
        slither = Slither(file_path)

        # Find all contracts that might contain the implementation
        all_contracts = slither.contracts
        target_contract = None
        target_function = None

        print(f"\nSearching for {contract_name}.{function_name}")

        # First look in the specified contract
        target_contract = next((c for c in all_contracts if c.name == contract_name), None)
        if target_contract:
            print(f"\nFound contract {contract_name}")

            # First try to find the function in the contract itself
            target_function = next(
                (f for f in target_contract.functions_declared
                 if f.name == function_name and hasattr(f, 'source_mapping')),
                None
            )

            # If not found in declared functions, check inherited functions
            if not target_function:
                for contract in target_contract.inheritance:
                    target_function = next(
                        (f for f in contract.functions_declared
                         if f.name == function_name and hasattr(f, 'source_mapping')),
                        None
                    )
                    if target_function:
                        target_contract = contract
                        break

            # Only if not found in contract hierarchy, look for library implementations
            if not target_function:
                print("\nSearching in libraries...")
                for contract in all_contracts:
                    if contract.is_library:
                        for func in contract.functions:
                            if func.name == function_name and hasattr(func, 'source_mapping'):
                                library_impl = func
                                # Store library implementation as fallback
                                if not target_function:
                                    target_function = library_impl
                                    target_contract = contract

        if not target_function:
            print(f"\nFunction {function_name} implementation not found")
            return

        print(f"\nFound implementation in {target_contract.name}")

        # Build call graph
        graph = CallGraph()
        collect_calls(target_function, target_contract, graph)

        # Print execution order
        print_execution_order(graph, function_name)

    except Exception as e:
        print(f"Error analyzing function: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

def get_contract_source(contract_path: str, function_name: str) -> Optional[str]:
    """Try to get source code for a function from the contract file"""
    try:
        with open(contract_path, 'r') as f:
            source = f.read()
            func_start = source.find(f"function {function_name}")
            if func_start != -1:
                brace_start = source.find("{", func_start)
                if brace_start != -1:
                    brace_count = 1
                    pos = brace_start + 1
                    while brace_count > 0 and pos < len(source):
                        if source[pos] == "{":
                            brace_count += 1
                        elif source[pos] == "}":
                            brace_count -= 1
                        pos += 1
                    if brace_count == 0:
                        return source[func_start:pos]
    except Exception:
        pass

def main():
    parser = argparse.ArgumentParser(description='Analyze Solidity contract function calls')
    parser.add_argument('file', help='Solidity file path')
    parser.add_argument('--list-contracts', action='store_true', help='List all contracts in the file')
    parser.add_argument('--contract', help='Contract name to analyze')
    parser.add_argument('--list-functions', action='store_true', help='List all functions in the contract')
    parser.add_argument('--function', help='Function name to analyze')

    args = parser.parse_args()

    if args.list_contracts:
        list_contracts(args.file)
        return

    if args.contract and args.list_functions:
        list_functions(args.file, args.contract)
        return

    if args.contract and args.function:
        analyze_function(args.file, args.contract, args.function)
        return

    parser.print_help()

if __name__ == "__main__":
    main()
