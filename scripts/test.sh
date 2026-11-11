#!/usr/bin/env bash

export PYTHONPATH=src/:$PYTHONPATH
export DATABASE_URL=sqlite:///test.db
export API_KEY=testing

# Run Tests
uv run pytest --cov src --cov-branch --cov-report=xml --junitxml=junit.xml -o junit_family=legacy
