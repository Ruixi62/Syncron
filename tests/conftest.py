import os


def pytest_sessionfinish(session, exitstatus):
    """Evite le segfault de Qt a la fermeture de l'interpreteur en CI."""
    if os.environ.get("CI"):
        os._exit(int(exitstatus))
