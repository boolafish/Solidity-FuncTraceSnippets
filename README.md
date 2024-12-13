# Solidity-FuncTraceSnippets

A tool that helps generate code snippets of nested function calls in Solidity smart contracts.

## Description

This tool analyzes Solidity smart contracts and generates code snippets showing the trace of nested function calls, making it easier to understand and visualize function interactions within your contracts.

## Dependencies

- Python 3.7 or higher
- [Slither](https://github.com/crytic/slither) - A Solidity static analysis framework

### To run the command

To see all the options, run:
```bash
python fun-trace-snippet.py --help
```

To generate a snippet, run:

```bash
python fun-trace-snippet.py --contract-name <contract-name> --function-name <function-name>
```

For instance:

```
python fun-trace-snippet.py examples/GameToken.sol --contract GameToken --function rewardPlayer
```

## License

MIT License

