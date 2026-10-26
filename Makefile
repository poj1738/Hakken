.DEFAULT_GOAL := help
PY := python3
VENV := .venv
VENV_PY := $(VENV)/bin/python

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: ## Create .venv and install pinned dependencies
	$(PY) -m venv $(VENV)
	$(VENV_PY) -m pip install --quiet --upgrade pip
	$(VENV_PY) -m pip install --quiet -r requirements.txt
	$(VENV_PY) scripts/secret_scan.py --install
	@echo "setup done. Copy .env.example to .env and fill it in."

preflight: ## Read-only check of tools, env names, Zetaris and Nightshift
	$(PY) scripts/preflight.py

test: ## Run the test suite
	$(VENV_PY) -m pytest

conformance: ## Run only the ported engine conformance tests (none ported yet)
	@if ls tests/engines/test_*.py >/dev/null 2>&1; then $(VENV_PY) -m pytest tests/engines; \
	else echo "not implemented yet: no engine conformance tests in tests/engines/"; exit 2; fi

scan: ## Scan every tracked file for secrets
	$(PY) scripts/secret_scan.py --all

run: ## One run straight through (example_2; example_1 stops at the identity review)
	$(VENV_PY) run.py --input input_examples/example_2.json

serve: ## Start the API server
	$(VENV_PY) run.py serve

data: ## Rebuild the reference data (PBS fetch, then lexicon)
	$(VENV_PY) scripts/fetch_reference.py
	$(VENV_PY) scripts/build_lexicon.py

lexicon: ## Rebuild only the lexicon, from the committed hand-built sources
	$(VENV_PY) scripts/build_lexicon.py

synth: ## Regenerate the synthetic silos, ground truth and fixtures
	$(VENV_PY) scripts/generate_synthetic.py
	@echo
	@echo "data/synthetic/silos/ is gitignored and NOTHING ELSE creates it."
	@echo "If Zetaris is registered, follow this with:  make refresh"

register: ## Show the Zetaris registration statements (dry run, sends nothing)
	$(VENV_PY) scripts/register_sources.py

refresh: ## Re-cache the Zetaris tables after `make synth` (creates/drops nothing)
	$(VENV_PY) scripts/register_sources.py --refresh

verify: ## Check the live Zetaris views against the files and the committed fixtures
	$(VENV_PY) scripts/register_sources.py --verify-only

examples: ## Regenerate output_examples/ from real runs (needs the agent loop)
	@if [ -f scripts/generate_examples.py ]; then $(VENV_PY) scripts/generate_examples.py; \
	else echo "not implemented yet: scripts/generate_examples.py arrives with the agent loop"; exit 2; fi

validate: ## Reproduce the disqualification checklist end to end
	@if [ -f scripts/validate_submission.sh ]; then bash scripts/validate_submission.sh; \
	else echo "not implemented yet: scripts/validate_submission.sh"; exit 2; fi

.PHONY: help setup preflight test conformance scan data lexicon synth run serve register refresh verify examples validate
