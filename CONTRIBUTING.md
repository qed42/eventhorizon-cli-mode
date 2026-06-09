# Contributing to EventHorizon CLI

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

```Shell
# Clone the repo
git clone https://github.com/qed42/eventhorizon-cli.git
cd eventhorizon-cli

# One-command setup (creates venv + installs dev deps)
source setup.sh

# Or manually:
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```Shell
pytest tests/ -v
```

## Adding a New Rule

Rules live in `src/eventhorizon/scanner/rules/custom_rules.yml`. Each rule follows this format:

```YAML
- id: rule_id_string
  pattern: "regex_pattern"
  file_types: [".php", ".module"]
  severity: error|warning|info
  category: security|performance
  message: "Human-readable explanation of the issue."
```

After adding a rule, add a corresponding test case in `tests/`.

## Code Style

* Python 3.9+ compatible
* Type hints on all function signatures
* Use `pathlib.Path` for file operations
* Lint with `ruff check src/ tests/`

## Pull Request Process

1. Fork the repo and create a feature branch
2. Make your changes with tests
3. Run `pytest` and `ruff check` to ensure everything passes
4. Submit a PR with a clear description of the change

## License of Contributions

By submitting a contribution, you agree that your work is licensed under the
project's [MIT License](LICENSE) and that you have the right to license it. We
use the [Developer Certificate of Origin](https://developercertificate.org/) —
please sign off your commits with `git commit -s` (`Signed-off-by:` line) to
certify that you wrote the code or otherwise have the right to submit it.

