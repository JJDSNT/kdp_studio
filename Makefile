# KDP Studio — one command per thing someone needs on the first day.

BOOK ?= examples/sample-book
PORT ?= 8765

.DEFAULT_GOAL := setup
.PHONY: setup ui test lint check serve assistant doctor

setup:            ## environment with every extra, then what works here
	uv sync --all-extras
	uv run kdp doctor

ui:               ## build the control room and the Copilot Runtime (needs Node 20+)
	cd frontend && npm install && npm run build

test:             ## the full suite
	uv run pytest
	uv run flake8 src tests tools

check:            ## build and measure the sample book
	uv run kdp build $(BOOK) && uv run kdp check $(BOOK)

serve:            ## the control room on BOOK
	uv run kdp serve $(BOOK) --port $(PORT)

assistant:        ## the control room on BOOK, with the assistant
	uv run kdp serve $(BOOK) --port $(PORT) --assistant

doctor:
	uv run kdp doctor
