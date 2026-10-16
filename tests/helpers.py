import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "sherlock", "scripts")


def script(name):
    return os.path.join(SCRIPTS, name + ".py")


def load(name):
    spec = importlib.util.spec_from_file_location(name, script(name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path, encoding="utf-8"):
    with open(path, encoding=encoding) as f:
        return f.read()
