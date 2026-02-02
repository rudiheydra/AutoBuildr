#!/bin/bash
# Docker HEALTHCHECK probe
# Hits GET /api/health (server/main.py:213)
curl -sf http://localhost:8888/api/health || exit 1
