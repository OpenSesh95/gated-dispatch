.PHONY: test lint run
test:
	python -m pytest -q
lint:
	python -m compileall -q src || true
run:
	@echo "Set the project's entry point here (canonical skeleton: src/main.py)."
