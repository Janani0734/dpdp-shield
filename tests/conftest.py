import dataclasses
from pathlib import Path

import pytest

from dpdp_shield.config import Settings
from dpdp_shield.pipeline import Shield

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


@pytest.fixture()
def settings(tmp_path):
    # force offline mode regardless of the developer's environment
    return dataclasses.replace(Settings.from_env(), gemini_api_key="", data_dir=tmp_path)


@pytest.fixture()
def shield(settings):
    return Shield(settings)


@pytest.fixture()
def bad_pdf():
    return (SAMPLES / "bad_policy.pdf").read_bytes()


@pytest.fixture()
def good_pdf():
    return (SAMPLES / "good_policy.pdf").read_bytes()
