import os
import sys
import tempfile
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import portable as portable_mode


def test_portable_marker():
    with tempfile.TemporaryDirectory() as tmp:
        orig_dir = os.getcwd()
        try:
            os.chdir(tmp)
            assert portable_mode.is_portable() is False
            result = portable_mode.enable_portable_mode(tmp)
            assert result is True
            assert portable_mode.is_portable() is True
            portable_mode.disable_portable_mode(tmp)
            assert portable_mode.is_portable() is False
        finally:
            os.chdir(orig_dir)


def test_get_data_dir():
    with tempfile.TemporaryDirectory() as tmp:
        orig_dir = os.getcwd()
        try:
            os.chdir(tmp)
            data_dir = portable_mode.get_data_dir(tmp)
            assert os.path.exists(data_dir)
        finally:
            os.chdir(orig_dir)


def test_get_minecraft_dir():
    with tempfile.TemporaryDirectory() as tmp:
        orig_dir = os.getcwd()
        try:
            os.chdir(tmp)
            mc_dir = portable_mode.get_minecraft_dir(tmp)
            assert os.path.exists(mc_dir)
        finally:
            os.chdir(orig_dir)


if __name__ == "__main__":
    test_portable_marker()
    test_get_data_dir()
    test_get_minecraft_dir()
    print("All portable tests passed!")
