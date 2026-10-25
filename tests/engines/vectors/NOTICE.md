# Third-party test vectors

`hmem_vectors.json` is a **verbatim copy** of
`engines/hmem/conformance/vectors/vectors.json` from the Meterless repository
(github.com/Meterless/Meterless, commit `1742dec`), licensed under the
**Apache License, Version 2.0**. Unmodified. `tests/engines/test_hmem_conformance.py`
ports the official runner (`conformance/runner.ts`) that consumes it.

The World Model conformance cases have no vectors file; they are inline in its runner
and ported in `tests/engines/test_world_model_conformance.py`.
