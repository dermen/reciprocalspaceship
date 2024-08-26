import logging
import warnings
from importlib.util import find_spec


def set_ray_loglevel(level):
    logger = logging.getLogger("ray")
    logger.setLevel(level)
    for handler in logger.handlers:
        handler.setLevel(level)


def check_for_ray():
    has_ray = True
    if find_spec("ray") is None:
        has_ray = False

        message = (
            "ray (https://www.ray.io/) is not available..."
            "Falling back to serial stream file parser."
        )
        warnings.warn(message, ImportWarning)
    return has_ray


def check_for_mpi():
    try:
        from mpi4py import MPI

        return True
    except Exception as err:
        message = (
            f"Failed `from mpi4py import MPI` with {err}. Falling back to serial mode."
        )
        warnings.warn(message, ImportWarning)
        return False
