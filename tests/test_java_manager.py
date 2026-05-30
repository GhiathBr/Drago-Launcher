import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from java_manager import get_java_for_mc_version


def test_java_for_mc_versions():
    assert get_java_for_mc_version("1.8.9") == 8
    assert get_java_for_mc_version("1.12.2") == 8
    assert get_java_for_mc_version("1.16.5") == 8
    assert get_java_for_mc_version("1.17") == 17
    assert get_java_for_mc_version("1.18.2") == 17
    assert get_java_for_mc_version("1.19.4") == 17
    assert get_java_for_mc_version("1.20.1") == 17
    assert get_java_for_mc_version("1.20.4") == 17
    assert get_java_for_mc_version("1.20.5") == 21
    assert get_java_for_mc_version("1.21") == 21
    assert get_java_for_mc_version("1.21.4") == 21


def test_unknown_version_defaults_to_17():
    assert get_java_for_mc_version("0.0.0") == 17
    assert get_java_for_mc_version("99.99") == 21


if __name__ == "__main__":
    test_java_for_mc_versions()
    test_unknown_version_defaults_to_17()
    print("All java_manager tests passed!")
