#!/bin/bash
rq worker --url ${REDIS_URL:-redis://valkey:6379}
