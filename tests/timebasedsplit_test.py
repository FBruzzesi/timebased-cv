from contextlib import nullcontext as does_not_raise
from datetime import date, datetime, timedelta
from typing import Tuple

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import Ridge
from sklearn.model_selection import RandomizedSearchCV

from timebasedcv import TimeBasedCVSplitter, TimeBasedSplit, _CoreTimeBasedSplit

RNG = np.random.default_rng()

# Define a fix set of valid arguments
valid_kwargs = {
    "frequency": "days",
    "train_size": 7,
    "forecast_horizon": 3,
    "gap": 0,
    "stride": 2,
    "window": "rolling",
}


start_dt = pd.Timestamp(2023, 1, 1)
end_dt = pd.Timestamp(2023, 3, 31)

time_series = pd.Series(pd.date_range(start_dt, end_dt, freq="D"))
size = len(time_series)

df = pd.DataFrame(data=RNG.normal(size=(size, 2)), columns=["a", "b"]).assign(  # noqa: PD901
    date=time_series,
    y=lambda t: t[["a", "b"]].sum(axis=1),
)

X, y = df[["a", "b"]], df["y"]

err_msg_freq = (
    r"`frequency` must be one of \('days', 'seconds', 'microseconds', 'milliseconds', 'minutes', 'hours', 'weeks'\)"
)
err_msg_int = r"\(`train_size_`, `forecast_horizon_`, `gap_`, `stride_`\) arguments must be of type `int`."
err_msg_lower_bound = r"must be greater or equal than \(1, 1, 0, 1\)"
err_msg_window = r"`window` must be one of \('rolling', 'expanding'\)"
err_msg_time_order = r"(`time_start` must be before `time_end`)|(`start_dt` must be before `end_dt`)."
err_msg_no_time = r"Either `time_series` or \(`start_dt`, `end_dt`\) pair must be provided."
err_msg_shape = "Invalid shape: "
# Tests for _CoreTimeBasedSplit


@pytest.mark.parametrize(
    "arg_name, arg_value, context",
    [
        ("frequency", "days", does_not_raise()),
        ("frequency", "hours", does_not_raise()),
        ("frequency", "test", pytest.raises(ValueError, match=err_msg_freq)),
        ("frequency", 123, pytest.raises(ValueError, match=err_msg_freq)),
        ("train_size", 7, does_not_raise()),
        ("train_size", 1.0, pytest.raises(TypeError, match=err_msg_int)),
        ("train_size", "test", pytest.raises(TypeError, match=err_msg_int)),
        ("train_size", -123, pytest.raises(ValueError, match=err_msg_lower_bound)),
        ("forecast_horizon", 7, does_not_raise()),
        ("forecast_horizon", 1.0, pytest.raises(TypeError, match=err_msg_int)),
        ("forecast_horizon", "test", pytest.raises(TypeError, match=err_msg_int)),
        ("forecast_horizon", -123, pytest.raises(ValueError, match=err_msg_lower_bound)),
        ("gap", 0, does_not_raise()),
        ("gap", 7, does_not_raise()),
        ("gap", 1.0, pytest.raises(TypeError, match=err_msg_int)),
        ("gap", "test", pytest.raises(TypeError, match=err_msg_int)),
        ("gap", -123, pytest.raises(ValueError, match=err_msg_lower_bound)),
        ("stride", None, does_not_raise()),
        ("stride", 7, does_not_raise()),
        ("stride", 1.0, pytest.raises(TypeError, match=err_msg_int)),
        ("stride", "test", pytest.raises(TypeError, match=err_msg_int)),
        ("stride", -1, pytest.raises(ValueError, match=err_msg_lower_bound)),
        ("window", "rolling", does_not_raise()),
        ("window", "expanding", does_not_raise()),
        ("window", "test", pytest.raises(ValueError, match=err_msg_window)),
        ("window", 123, pytest.raises(ValueError, match=err_msg_window)),
    ],
)
def test_core_init(arg_name, arg_value, context):
    """
    Tests initialization of _CoreTimeBasedSplit with different input values.
    """
    with context:
        _CoreTimeBasedSplit(
            **{
                **valid_kwargs,
                arg_name: arg_value,
            },
        )


def test_core_repr():
    """
    Tests the __repr__ method of _CoreTimeBasedSplit.
    """
    obj = _CoreTimeBasedSplit(**valid_kwargs)

    assert repr(obj) == (
        "_CoreTimeBasedSplit("
        f"\n    frequency_ = {valid_kwargs['frequency']}"
        f"\n    train_size_ = {valid_kwargs['train_size']}"
        f"\n    forecast_horizon_ = {valid_kwargs['forecast_horizon']}"
        f"\n    gap_ = {valid_kwargs['gap']}"
        f"\n    stride_ = {valid_kwargs['stride']}"
        f"\n    window_ = {valid_kwargs['window']}"
        "\n)"
    )


@pytest.mark.parametrize(
    "frequency, train_size, forecast_horizon, gap, stride",
    [("days", 7, 7, 1, None), ("hours", 48, 24, 0, 2), ("weeks", 4, 1, 1, 1)],
)
def test_core_properties(frequency, train_size, forecast_horizon, gap, stride):
    """
    Tests the properties of _CoreTimeBasedSplit.
    """
    cv = _CoreTimeBasedSplit(
        frequency=frequency,
        train_size=train_size,
        forecast_horizon=forecast_horizon,
        gap=gap,
        stride=stride,
    )

    assert cv.train_delta == timedelta(**{frequency: train_size})
    assert cv.forecast_delta == timedelta(**{frequency: forecast_horizon})
    assert cv.gap_delta == timedelta(**{frequency: gap})
    assert cv.stride_delta == timedelta(**{frequency: stride or forecast_horizon})


@pytest.mark.parametrize(
    "window",
    ["rolling", "expanding"],
)
@pytest.mark.parametrize(
    "time_start, time_end, context",
    [
        (datetime(2023, 1, 1), datetime(2023, 1, 31), does_not_raise()),
        (datetime(2023, 1, 1), datetime(2023, 1, 1), pytest.raises(ValueError, match=err_msg_time_order)),
        (date(2023, 1, 1), date(2023, 1, 31), does_not_raise()),
        (date(2023, 1, 1), date(2023, 1, 1), pytest.raises(ValueError, match=err_msg_time_order)),
        (pd.Timestamp(2023, 1, 1), pd.Timestamp(2023, 1, 31), does_not_raise()),
        (pd.Timestamp(2023, 1, 1), pd.Timestamp(2023, 1, 1), pytest.raises(ValueError, match=err_msg_time_order)),
    ],
)
def test_core_splits_from_period(window, time_start, time_end, context):
    """Tests the _CoreTimeBasedSplit._splits_from_period method."""

    cv = _CoreTimeBasedSplit(
        **{
            **valid_kwargs,
            "window": window,
        },
    )

    with context:
        n_splits = 0
        current_time = time_start
        for split_state in cv._splits_from_period(time_start, time_end):  # noqa: SLF001
            train_start = current_time if cv.window_ == "rolling" else time_start
            train_end = current_time + cv.train_delta
            forecast_start = train_end + cv.gap_delta
            forecast_end = forecast_start + cv.forecast_delta

            assert split_state.train_start == train_start
            assert split_state.train_end == train_end
            assert split_state.forecast_start == forecast_start
            assert split_state.forecast_end == forecast_end

            current_time = current_time + cv.stride_delta
            n_splits += 1

        assert n_splits == cv.n_splits_of(start_dt=time_start, end_dt=time_end)


@pytest.mark.parametrize(
    "kwargs, context",
    [
        ({"time_series": time_series}, does_not_raise()),
        ({"start_dt": date(2023, 1, 1), "end_dt": date(2023, 1, 31)}, does_not_raise()),
        ({"time_series": None, "start_dt": date(2023, 1, 1)}, pytest.raises(ValueError, match=err_msg_no_time)),
        ({"time_series": None, "end_dt": date(2023, 1, 31)}, pytest.raises(ValueError, match=err_msg_no_time)),
        (
            {"start_dt": date(2023, 1, 31), "end_dt": date(2023, 1, 1)},
            pytest.raises(ValueError, match=err_msg_time_order),
        ),
    ],
)
def test_core_n_splits_of(kwargs, context):
    """
    Tests the _CoreTimeBasedSplit.n_splits_of method.
    """
    cv = _CoreTimeBasedSplit(**valid_kwargs)

    with context:
        cv.n_splits_of(**kwargs)


# Tests for TimeBasedSplit


@pytest.mark.parametrize(
    "kwargs",
    [
        {"arrays": ()},  # empty arrays
        {"arrays": (X, y[:-1])},  # arrays different shape
        {"time_series": time_series[:-1]},
        # arrays shape different from time_series shape
        {"start_dt": pd.Timestamp(2023, 1, 1), "end_dt": pd.Timestamp(2023, 1, 1)},
    ],
)
def test_timebasedcv_split_invalid(kwargs):
    """
    Test the TimeBasedSplit.split method with invalid arguments.
    """
    cv = TimeBasedSplit(**valid_kwargs)
    arrays_ = kwargs.get("arrays", (X, y))
    time_series_ = kwargs.get("time_series", time_series)
    start_dt_ = kwargs.get("start_dt")
    end_dt_ = kwargs.get("end_dt")

    with pytest.raises(ValueError):  # noqa: PT011
        next(cv.split(*arrays_, time_series=time_series_, start_dt=start_dt_, end_dt=end_dt_))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"arrays": (X,)},
        {"arrays": (X, y, X.to_numpy())},  # multi-type arrays
        # arrays shape different from time_series shape
        {"start_dt": pd.Timestamp(2023, 1, 1), "end_dt": pd.Timestamp(2023, 1, 31)},
        {"return_splitstate": True},
    ],
)
def test_timebasedcv_split(kwargs):
    """Tests the TimeBasedSplit.split method."""
    cv = TimeBasedSplit(**valid_kwargs)

    arrays_ = kwargs.get("arrays", (X, y))
    time_series_ = kwargs.get("time_series", time_series)
    start_dt_ = kwargs.get("start_dt")
    end_dt_ = kwargs.get("end_dt")
    return_splitstate_ = kwargs.get("return_splitstate", False)

    n_arrays = len(arrays_)
    split_results = next(
        cv.split(
            *arrays_,
            time_series=time_series_,
            start_dt=start_dt_,
            end_dt=end_dt_,
            return_splitstate=return_splitstate_,
        ),
    )

    if return_splitstate_:
        train_forecast, _ = split_results
    else:
        train_forecast = split_results

    assert len(train_forecast) == n_arrays * 2


# Tests for TimeBasedCVSplitter


def test_cv_splitter():
    """
    Tests the TimeBasedCVSplitter `__init__` and `split` methods as well as its
    compatibility with sklearn's _CV Splitter_s.
    """
    cv = TimeBasedCVSplitter(
        time_series=time_series,
        start_dt=start_dt,
        end_dt=end_dt,
        **valid_kwargs,
    )

    assert cv.time_series_ is not None
    assert cv.start_dt_ is not None
    assert cv.end_dt_ is not None
    assert isinstance(cv.n_splits, int)
    assert isinstance(cv.size_, int)

    param_grid = {
        "alpha": np.linspace(0.1, 2, 10),
        "fit_intercept": [True, False],
        "positive": [True, False],
    }

    random_search_cv = RandomizedSearchCV(
        estimator=Ridge(),
        param_distributions=param_grid,
        cv=cv,
        n_jobs=-1,
    ).fit(X, y)

    assert random_search_cv.best_estimator_ is not None


@pytest.mark.parametrize("size", [size])
@pytest.mark.parametrize(
    "X_shape, y_shape, g_shape, context",
    [
        ((size, 2), (size,), (size, 2), does_not_raise()),
        ((size + 1, 2), (size,), (size, 2), pytest.raises(ValueError, match=err_msg_shape)),
        ((size, 2), (size + 1,), (size, 2), pytest.raises(ValueError, match=err_msg_shape)),
        ((size, 2), (size,), (size + 1, 2), pytest.raises(ValueError, match=err_msg_shape)),
    ],
)
def test_cv_splitter_validate_split(
    size: int,
    X_shape: Tuple[int, int],
    y_shape: Tuple[int],
    g_shape: Tuple[int, int],
    context,
):
    """Test the TimeBasedCVSplitter._validate_split_args static method."""

    with context:
        TimeBasedCVSplitter._validate_split_args(  # noqa: SLF001
            size=size,
            X=RNG.normal(size=X_shape),
            y=RNG.normal(size=y_shape),
            groups=RNG.normal(size=g_shape),
        )
