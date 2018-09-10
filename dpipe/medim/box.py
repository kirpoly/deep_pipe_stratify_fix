"""Functions to work with boxes: immutable numpy arrays of shape (start, stop) that represent borders of the rectangle.
Left is inclusive, right is non-inclusive, so this box can be used as `build_slices(box[0], box[1])`.
 All boxes are immutable."""
import itertools
from functools import wraps

import numpy as np

from .types import AxesLike
from .checks import check_len
from .shape_utils import compute_shape_from_spatial, shape_after_full_convolution
from .axes import fill_by_indices
from .utils import build_slices


def make_box_(iterable):
    """Returns `box`, generated inplace from the `iterable`. If `iterable` was a numpy array, will make it
    immutable and return."""
    box = np.asarray(iterable)
    box.setflags(write=False)

    assert box.ndim == 2 and len(box) == 2, box.shape
    assert np.all(box[0] <= box[1]), box

    return box


def get_box_volume(box):
    return np.prod(box[1] - box[0], axis=0)


def returns_box(func):
    """Returns function, decorated so that it returns a box."""

    @wraps(func)
    def func_returning_box(*args, **kwargs):
        return make_box_(func(*args, **kwargs))

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


@returns_box
def get_random_box(shape: AxesLike, box_shape: AxesLike, axes: AxesLike = None):
    """Get a random box of corresponding shape that fits in the `shape` along the given axes."""
    start = np.stack(map(np.random.randint, shape_after_full_convolution(shape, box_shape, axes)))
    return start, start + fill_by_indices(shape, box_shape, axes)


def box2slices(box):
    return build_slices(*box)


def get_boxes_grid(shape: AxesLike, box_size: AxesLike, stride: AxesLike, axes: AxesLike = None, valid: bool = True):
    """
    A convolution-like approach to generating slices from a tensor.

    Parameters
    ----------
    shape
        the input tensor's shape.
    box_size
    axes
        axes along which the slices will be taken.
    stride
        the stride (step-size) of the slice.
    valid
        whether boxes of size smaller than ``box_size`` should be left out.
    """
    final_shape = shape_after_full_convolution(shape, box_size, axes, stride, valid=valid)
    box_size, stride = np.broadcast_arrays(box_size, stride)
    full_box = fill_by_indices(shape, box_size, axes)
    full_stride = fill_by_indices(np.ones_like(shape), stride, axes)

    for start in np.ndindex(*final_shape):
        start = np.asarray(start) * full_stride
        yield make_box_([start, np.minimum(start + full_box, shape)])
