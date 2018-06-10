import numpy as np

from dpipe.medim.utils import squeeze_first


def iterate_slices(*data: np.ndarray, axis: int = -1):
    """Iterate over slices of a series of tensors along a given axis."""

    size = data[0].shape[axis]
    if any(x.shape[axis] != size for x in data):
        raise ValueError('All the tensors must have the same size along the given axis')

    for idx in range(size):
        yield squeeze_first(tuple(x.take(idx, axis=axis) for x in data))
