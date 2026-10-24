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
	$(VENV_PY) -m pytest -q

conformance: ## Run only the ported engine conformance tests
	$(VENV_PY) -m pytest -q tests/engines

scan: ## Scan every tracked file for secrets
	$(PY) scripts/secret_scan.py --all

run: ## One run against the first example input
	$(VENV_PY) run.py --input input_examples/example_1.json

serve: ## Start the API server
	$(VENV_PY) run.py serve

data: ## Rebuild the reference data (PBS fetch, then lexicon)
	$(VENV_PY) scripts/fetch_reference.py
	$(VENV_PY) scripts/build_lexicon.py

lexicon: ## Rebuild only the lexicon, from the committed hand-built sources
	$(VENV_PY) scripts/build_lexicon.py

synth: ## Regenerate the synthetic silos, ground truth and fixtures
	$(VENV_PY) scripts/generate_synthetic.py

register: ## Register the synthetic silos in Zetaris (dry-run first)
	$(VENV_PY) scripts/register_sources.py --dry-run

examples: ## Regenerate output_examples/ from real runs
	$(VENV_PY) scripts/generate_examples.py

validate: ## Reproduce the disqualification checklist end to end
	bash scripts/validate_submission.sh

.PHONY: help setup preflight test conformance scan data lexicon synth run serve register examples validate
