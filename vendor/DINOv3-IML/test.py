"""
Local evaluation entry point for DINOv3-IML.

This wrapper imports the repository's model package before delegating to
IMDLBenCo so custom models are registered in MODELS.
"""

import runpy

import models  # noqa: F401


if __name__ == "__main__":
    runpy.run_module("IMDLBenCo.training_scripts.test", run_name="__main__")
