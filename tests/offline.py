"""Valeurs fictives deterministes, reservees aux suites sans acces cluster."""

import os
import tempfile
_TEST_STATE = tempfile.TemporaryDirectory(prefix="romeo-offline-")
os.environ["ROMEO_MCP_DB"] = os.path.join(_TEST_STATE.name, "jobs.db")

os.environ.update(
    ROMEO_ACCOUNT="test-project", ROMEO_HOST="invalid-offline-host", ROMEO_QOS="normal",
    ROMEO_MAX_CPUS="1024", ROMEO_MAX_GPUS="16", ROMEO_MAX_JOBS="80",
)
