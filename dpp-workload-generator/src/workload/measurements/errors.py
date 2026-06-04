"""Benchmark-specific exceptions."""


class MeasurementError(RuntimeError):
    """Base class for measurement failures."""


class BenchmarkSetupError(MeasurementError):
    """Raised when benchmark setup cannot be completed."""


class ResolveBenchmarkError(MeasurementError):
    """Raised when a resolve benchmark call fails."""

