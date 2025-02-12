import multiprocessing
from functools import partial
from itertools import islice
from typing import Iterable, Callable, Union

import numpy as np

from ..itertools import zip_equal
from ..im.axes import AxesParams
from .utils import pad_batch_equal

__all__ = [
    'Infinite',
    'Threads', 'Loky', 'Iterator',
    'combine_batches', 'combine_to_arrays', 'combine_pad',
]


def combine_batches(inputs):
    """
    Combines tuples from ``inputs`` into batches: [(x, y), (x, y)] -> [(x, x), (y, y)]
    """
    return tuple(zip_equal(*inputs))


def combine_to_arrays(inputs):
    """
    Combines tuples from ``inputs`` into batches of numpy arrays.
    """
    return tuple(map(np.array, combine_batches(inputs)))


def combine_pad(inputs, padding_values: AxesParams = 0, ratio: AxesParams = 0.5):
    """
    Combines tuples from ``inputs`` into batches and pads each batch in order to obtain
    a correctly shaped numpy array.
    
    Parameters
    ----------
    inputs
    padding_values
        values to pad with. If Callable (e.g. `numpy.min`) - ``padding_values(x)`` will be used.
    ratio
        the fraction of the padding that will be applied to the left, ``1.0 - ratio`` will be applied to the right.
        By default ``0.5 - ratio``, it is applied uniformly to the left and right.
        
    References
    ----------
    `pad_to_shape`
    """
    batches = combine_batches(inputs)
    padding_values = np.broadcast_to(padding_values, [len(batches)])
    return tuple(pad_batch_equal(x, values, ratio) for x, values in zip(batches, padding_values))


class Transform:
    component = None


class Infinite:
    """
    Combine ``source`` and ``transformers`` into a batch iterator that yields batches of size ``batch_size``.

    Parameters
    ----------
    source: Iterable
        an infinite iterable.
    transformers: Callable
        the callable that transforms the objects generated by the previous element of the pipeline.
    batch_size: int, Callable
        the size of batch.
    batches_per_epoch: int
        the number of batches to yield each epoch.
    buffer_size: int
        the number of objects to keep buffered in each pipeline element. Default is 1.
    combiner: Callable
        combines chunks of single batches in multiple batches, e.g. combiner([(x, y), (x, y)]) -> ([x, x], [y, y]).
        Default is `combine_to_arrays`.
    kwargs:
        additional keyword arguments passed to the ``combiner``.

    References
    ----------
    See the :doc:`tutorials/batch_iter` tutorial for more details.
    """

    def __init__(self, source: Iterable, *transformers: Union[Callable, Transform],
                 batch_size: Union[int, Callable], batches_per_epoch: int,
                 buffer_size: int = 1, combiner: Callable = combine_to_arrays, **kwargs):
        if batches_per_epoch <= 0:
            raise ValueError(f'Expected a positive amount of batches per epoch, but got {batches_per_epoch}')

        self.batches_per_epoch = batches_per_epoch
        self.pipeline = wrap_pipeline(
            source, *transformers,
            self._make_stacker(batch_size), Threads(partial(combiner, **kwargs)),
            buffer_size=buffer_size
        )

    @staticmethod
    def _make_stacker(batch_size):
        if callable(batch_size):
            should_add = batch_size

        elif isinstance(batch_size, int):
            if batch_size <= 0:
                raise ValueError(f'`batch_size` must be greater than zero, not {batch_size}.')

            def should_add(chunk, item):
                return len(chunk) < batch_size

        else:
            raise TypeError(f'`batch_size` must be either int or callable, not {type(batch_size)}.')

        def stacker(iterable):
            chunk = []

            for value in iterable:
                if not chunk or should_add(chunk, value):
                    chunk.append(value)
                else:
                    yield chunk
                    chunk = [value]

            if chunk:
                yield chunk

        return Iterator(stacker)

    def close(self):
        """Stop all background processes."""
        self.__exit__(None, None, None)

    def __call__(self):
        if not self.pipeline.pipeline_active:
            self.__enter__()
        return islice(self.pipeline, self.batches_per_epoch)

    def __enter__(self):
        self.pipeline.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self.pipeline.__exit__(exc_type, exc_val, exc_tb)

    def __del__(self):
        self.close()


def wrap_pipeline(source, *transformers, buffer_size=1):
    from ._pdp import Pipeline, ComponentDescription, Source, One2One

    def wrap(o):
        if isinstance(o, Transform):
            return o.component
        if not isinstance(o, ComponentDescription):
            return One2One(o, buffer_size=buffer_size)
        return o

    if not isinstance(source, ComponentDescription):
        source = Source(source, buffer_size=buffer_size)

    return Pipeline(source, *map(wrap, transformers))


class Iterator(Transform):
    """
    Apply ``transform`` to the iterator of values that flow through the batch iterator.

    Parameters
    ----------
    transform: Callable(Iterable) -> Iterable
        a function that takes an iterable and yields transformed values.
    n_workers: int
        the number of threads to which ``transform`` will be moved.
    buffer_size: int
        the number of objects to keep buffered.
    args:
        additional positional arguments passed to ``transform``.
    kwargs:
        additional keyword arguments passed to ``transform``.

    References
    ----------
    See the :doc:`tutorials/batch_iter` tutorial for more details.
    """

    def __init__(self, transform: Callable, *args, n_workers: int = 1, buffer_size: int = 1, **kwargs):
        from ._pdp import ComponentDescription, start_iter

        assert n_workers > 0
        assert buffer_size > 0

        self.component = ComponentDescription(partial(
            start_iter, transform=transform, n_workers=n_workers, args=args, kwargs=kwargs
        ), n_workers, buffer_size)


class Threads(Iterator):
    """
    Apply ``func`` concurrently to each object in the batch iterator by moving it to ``n_workers`` threads.

    Parameters
    ----------
    transform: Callable(Iterable) -> Iterable
        a function that takes an iterable and yields transformed values.
    n_workers: int
        the number of threads to which ``transform`` will be moved.
    buffer_size: int
        the number of objects to keep buffered.
    args:
        additional positional arguments passed to ``transform``.
    kwargs:
        additional keyword arguments passed to ``transform``.

    References
    ----------
    See the :doc:`tutorials/batch_iter` tutorial for more details.
    """

    def __init__(self, func: Callable, *args, n_workers: int = 1, buffer_size: int = 1, **kwargs):
        def transform_map(iterable):
            for value in iterable:
                yield func(value, *args, **kwargs)

        super().__init__(transform_map, n_workers=n_workers, buffer_size=buffer_size)


class Loky(Transform):
    """
    Apply ``func`` concurrently to each object in the batch iterator by moving it to ``n_workers`` processes.

    Parameters
    ----------
    transform: Callable(Iterable) -> Iterable
        a function that takes an iterable and yields transformed values.
    n_workers: int
        the number of threads to which ``transform`` will be moved.
    buffer_size: int
        the number of objects to keep buffered.
    args:
        additional positional arguments passed to ``transform``.
    kwargs:
        additional keyword arguments passed to ``transform``.

    Notes
    -----
    Process-based parallelism is implemented with the ``loky`` backend.

    References
    ----------
    See the :doc:`tutorials/batch_iter` tutorial for more details.
    """

    def __init__(self, func: Callable, *args, n_workers: int = 1, buffer_size: int = 1, **kwargs):
        from ._pdp import start_loky, ComponentDescription

        if n_workers < 0:
            n_workers = max(1, multiprocessing.cpu_count() + n_workers + 1)

        assert n_workers > 0
        assert buffer_size > 0

        self.component = ComponentDescription(partial(
            start_loky, transform=func, n_workers=n_workers, args=args, kwargs=kwargs
        ), n_workers, buffer_size)
