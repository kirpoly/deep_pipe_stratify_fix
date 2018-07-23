"""Functions to work with boxes: immutable numpy arrays os shape (start, stop) that represent borders of the rectangle.
Left is inclusive, right is non-inclusive, so this box can be used as `build_slices(box[0], box[1])`.
 All boxes are immutable."""
import itertools
from functools import wraps

import numpy as np

from .checks import check_len
from .shape_utils import compute_shape_from_spatial


def make_box_(iterable):
    """Returns `box`, generated inplace from the `iterable`. If `iterable` was a numpy array, will make it
    immutable and return."""
    box = np.asarray(iterable)
    box.setflags(write=False)
    return box


def returns_box(func):
    """Returns function, decorated so that it returns a box."""

    @wraps(func)
    def func_returning_box(*args, **kwargs):
        box = np.asarray(func(*args, **kwargs))
        return make_box_(box)

    return func_returning_box


@returns_box
def broadcast_spatial_box(shape, spatial_box, spatial_dims):
    """Returns `box`, such that it contains `spatial_box` across `spatial_dims` and whole array
    with shape `shape` across other dimensions."""
    return (compute_shape_from_spatial([0] * len(shape), spatial_box[0], spatial_dims),
            compute_shape_from_spatial(shape, spatial_box[1], spatial_dims))


@returns_box
def limit_box(box, limit):
    """Returns `box`, maximum subset of the input `box` so that start would be non-negative and
    stop would be limited by the `limit`."""
    check_len(*box, limit)
    return np.maximum(box[0], 0), np.minimum(box[1], limit)


@returns_box
def get_box_padding(box: np.ndarray, limit):
    """Returns padding that is necessary to get `box` from array of shape `limit`.
     Returns padding in numpy form, so it can be given to `numpy.pad`."""
    check_len(*box, limit)
    return np.maximum([-box[0], box[1] - limit], 0).T


@returns_box
def add_margin(box: np.ndarray, margin):
    """Returns `box` with size increased by the `margin` (need to be broadcastable to the box)
    compared to the input `box`."""
    margin = np.broadcast_to(margin, box.shape)
    return box[0] - margin[0], box[1] + margin[1]


@returns_box
def get_centered_box(center: np.ndarray, box_size: np.ndarray):
    """Get box of size `box_size`, centered in the `center`.
    If `box_size` is odd, `center` will be closer to the right."""
    start = center - box_size // 2
    stop = center + box_size // 2 + box_size % 2
    return start, stop


@returns_box
def mask2bounding_box(mask: np.ndarray):
    """Find the smallest box that contains all true values of the mask, so that if
     you use them in slice() you will extract box with all true values."""
    assert mask.any(), "Mask have no True values."

    start, stop = [], []
    for ax in itertools.combinations(range(mask.ndim), mask.ndim - 1):
        nonzero = np.any(mask, axis=ax)
        if np.any(nonzero):
            left, right = np.where(nonzero)[0][[0, -1]]
        else:
            left, right = 0, 0
        start.insert(0, left)
        stop.insert(0, right + 1)
    return start, stop