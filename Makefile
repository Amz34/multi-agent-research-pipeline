# Multi-agent research pipeline — developer shortcuts.
PYTHON ?= python3
VENV   ?= .venv
TOPIC  ?= impact of AI agents on developer workflows

.PHONY: help venv test check run serve deploy preview clean

help:  ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-9s\033[0m %s\n", $$1, $$2}'

venv:  ## create the virtualenv and install requirements
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -r requirements.txt

test:  ## run the offline test suite (no network, no API key)
	$(VENV)/bin/python -m unittest discover -s tests -v

check:  ## compile every source file, then run the test suite
	$(VENV)/bin/python -m compileall -q .
	$(VENV)/bin/python -m unittest discover -s tests -q

run:  ## run one topic through the pipeline: make run TOPIC="..."
	$(VENV)/bin/python cli.py "$(TOPIC)"

serve:  ## start the HTTP API in the foreground (127.0.0.1:8088)
	$(VENV)/bin/python server.py

deploy:  ## install and start the systemd service (needs root)
	sudo bash deploy.sh

preview:  ## render the systemd unit without changing anything
	bash deploy.sh --dry-run

clean:  ## remove caches and run logs
	rm -rf __pycache__ agents/__pycache__ tests/__pycache__ logs
