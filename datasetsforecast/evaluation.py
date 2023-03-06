# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/evaluation.ipynb.

# %% auto 0
__all__ = ['accuracy']

# %% ../nbs/evaluation.ipynb 2
import pickle
from functools import partial
from inspect import signature
from typing import Any, Callable, Dict, List, Optional, Union

import numpy as np
import pandas as pd
import fugue.api as fa
from fugue import transform
from fugue.collections.yielded import Yielded
from fugue.constants import FUGUE_CONF_WORKFLOW_EXCEPTION_INJECT
from fugue.dataframe import DataFrame
from fugue.workflow import FugueWorkflow

# %% ../nbs/evaluation.ipynb 3
def _cotransform(
    df1: Any,
    df2: Any,
    using: Any,
    schema: Any = None,
    params: Any = None,
    partition: Any = None,
    engine: Any = None,
    engine_conf: Any = None,
    force_output_fugue_dataframe: bool = False,
    as_local: bool = False,
) -> Any:
    dag = FugueWorkflow(compile_conf={FUGUE_CONF_WORKFLOW_EXCEPTION_INJECT: 0})
    src = dag.create_data(df1).zip(dag.create_data(df2), partition=partition)
    tdf = src.transform(
        using=using,
        schema=schema,
        params=params,
        pre_partition=partition,
    )
    tdf.yield_dataframe_as("result", as_local=as_local)
    dag.run(engine, conf=engine_conf)
    result = dag.yields["result"].result  # type:ignore
    if force_output_fugue_dataframe or isinstance(df1, (DataFrame, Yielded)):
        return result
    return result.as_pandas() if result.is_local else result.native

# %% ../nbs/evaluation.ipynb 4
def _quantiles_from_levels(model_name, level):
    """Returns quantiles associated to `level` and the sorte columns of `model_name`"""
    level = sorted(level)
    alphas = [100 - lv for lv in level]
    quantiles = [alpha / 200 for alpha in reversed(alphas)]
    quantiles.extend([1 - alpha / 200 for alpha in alphas])
    cols = [f'{model_name}-lo-{lv}' for lv in reversed(level)]
    cols.extend([f'{model_name}-hi-{lv}' for lv in level])
    return np.array(quantiles), cols

# %% ../nbs/evaluation.ipynb 7
def _evaluate(
        df: pd.DataFrame, 
        df_train: pd.DataFrame,
        metrics: Optional[List[Callable]] = None,
        id_col: str = 'unique_id',
        time_col: str = 'ds',
        target_col: str = 'y',
        level: Optional[List] = None,
    ) -> pd.DataFrame:
    cols_to_rm = '|'.join([id_col, time_col, target_col, 'cutoff', 'lo', 'hi'])
    has_cutoff = 'cutoff' in df.columns
    models = df.loc[:, ~df.columns.str.contains(cols_to_rm)].columns
    y = df[target_col].values
    eval_ = {}
    for model in models:
        eval_[model] = {}
        for metric in metrics:
            y_hat = df[model].values
            metric_name = metric.__name__
            params = signature(metric).parameters
            if 'y_train' in params:
                if df_train is None:
                    raise Exception(f'Please provide `Y_df` to compute {metric_name}')
                eval_[model][metric_name] = metric(y, y_hat, y_train=df_train[target_col].values)
            elif 'quantiles' in params:
                if level is None:
                    raise Exception(
                        f'Please provide the `level` argument to compute {metric_name}. '
                    )
                quantiles, lv_cols = _quantiles_from_levels(model_name=model, level=level)
                y_hat_q = df[lv_cols].values
                eval_[model][metric_name] = metric(y, y_hat_q, quantiles=quantiles)
            elif ('y_hat_lo' in params) and ('y_hat_hi' in params):
                if level is None:
                    raise Exception(
                        f'Please provide the `level` argument to compute {metric_name}. '
                    )
                for lv in level:
                    y_hat_lo = df[f'{model}-lo-{lv}'].values
                    y_hat_hi = df[f'{model}-hi-{lv}'].values
                    eval_[model][f'{metric_name}-lv-{lv}'] = metric(y, y_hat_lo, y_hat_hi)
            elif 'y_hat_hi' in params:
                if level is None:
                    raise Exception(
                        f'Please provide the `level` argument to compute {metric_name}. '
                    )
                quantiles, lv_cols = _quantiles_from_levels(model_name=model, level=level)
                for q, lv_col in zip(quantiles, lv_cols):
                    y_hat_q = df[lv_col].values
                    eval_[model][f'{metric_name}-q-{q}'] = metric(y, y_hat_q)
            elif 'q' in params:
                if level is None:
                    raise Exception(
                        f'Please provide the `level` argument to compute {metric_name}. '
                    )
                quantiles, lv_cols = _quantiles_from_levels(model_name=model, level=level)
                for q, lv_col in zip(quantiles, lv_cols):
                    y_hat_q = df[lv_col].values
                    eval_[model][f'{metric_name}-q-{q}'] = metric(y, y_hat_q, q=q)
            else:
                eval_[model][metric_name] = metric(y, y_hat)
    eval_df = pd.DataFrame(eval_).rename_axis('metric').reset_index()
    if has_cutoff:
        eval_df.insert(0, 'cutoff', df['cutoff'].iloc[0])
    eval_df.insert(0, id_col, df[id_col].iloc[0])
    return eval_df

# %% ../nbs/evaluation.ipynb 8
def _evaluate_without_insample(
        df: pd.DataFrame, 
        metrics: Optional[List[Callable]] = None,
        id_col: str = 'unique_id',
        time_col: str = 'ds',
        target_col: str = 'y',
        level: Optional[List] = None,
    ) -> pd.DataFrame:
    return _evaluate(
        df=df, df_train=None, metrics=metrics, id_col=id_col, time_col=time_col,
        target_col=target_col, level=level,
    )

# %% ../nbs/evaluation.ipynb 9
def _schema_evaluate(
        df: DataFrame,
        id_col: str = 'unique_id',
        time_col: str = 'ds',
        target_col: str = 'y',
    ) -> str: 
    cols_to_rm = [id_col, time_col, target_col, 'cutoff', '-lo-', '-hi-']
    cols = fa.get_column_names(df)
    has_cutoff = 'cutoff' in cols
    models = [col for col in cols if not any(col_rm in col for col_rm in cols_to_rm)]
    str_models = ','.join([f"{model}:double" for model in models])
    schema = fa.get_schema(df)
    id_col_type = str(schema.get(id_col).type)
    cutoff_col_type = ''
    if has_cutoff:
        cutoff_col_type = str(schema.get('cutoff').type)
    schema = (
        f'{id_col}:{id_col_type},metric:string,'
        + (f'cutoff:{cutoff_col_type},' if has_cutoff else '')
        + str_models
    )
    return schema

# %% ../nbs/evaluation.ipynb 10
def _agg_evaluation(
        df_eval: pd.DataFrame, 
        agg_fn: Any, 
        agg_by: Any,
        id_col: str = 'unique_id',
    ) -> pd.DataFrame:
    cols_to_rm = '|'.join(agg_by + [id_col, 'metric', 'cutoff', '-lo-', '-hi-'])
    models = df_eval.loc[:, ~df_eval.columns.str.contains(cols_to_rm)].columns
    return df_eval.groupby(agg_by)[models].apply(agg_fn, axis=0).reset_index()

# %% ../nbs/evaluation.ipynb 11
def _schema_agg_evaluation(
        df: pd.DataFrame, 
        agg_by: Optional[List[str]] = None,
        id_col: str = 'unique_id',
    ) -> str:
    cols_to_rm = [id_col, 'metric', 'cutoff', '-lo-', '-hi-']
    cols = fa.get_column_names(df)
    models = [col for col in cols if col not in cols_to_rm]    
    str_models = ','.join([f'{model}:double' for model in models])
    schema = fa.get_schema(df)
    agg_by_types = [str(schema.get(col).type) for col in agg_by]
    schema = [f'{col}:{type_}' for col, type_ in zip(agg_by, agg_by_types)]
    schema = ','.join(schema) + ',' + str_models
    return schema

# %% ../nbs/evaluation.ipynb 15
def accuracy(
        Y_hat_df: pd.DataFrame,
        metrics: List[Callable],
        Y_test_df: Optional[pd.DataFrame] = None,
        Y_df: Optional[pd.DataFrame] = None,
        id_col: str = 'unique_id',
        time_col: str = 'ds',
        target_col: str = 'y',
        level: Optional[List] = None,
        agg_by: Optional[List[str]] = None,
        agg_fn: Callable = np.mean,
        engine: Any = None,
        **transform_kwargs: Any,
    ) -> pd.DataFrame:
    """Evaluate forecast using different metrics.
    
    Parameters
    ----------
    Y_hat_df : pandas DataFrame
        Forecasts and models to evaluate.
        Can contain the actual values given by `target_col`.
    metrics : List of Callables
        Functions with arguments `y`, `y_hat`, and optionally `y_train`.
    Y_test_df :  pandas DataFrame, optional (default=None)
        True values. 
        Nedded if `Y_hat_df` does not have the true values.
    Y_df : pandas DataFrame, optional (default=None)
        Training set. Used to evaluate metrics such as `mase`. 
    id_col : str (default='unique_id')
        Column that identifies each serie. If 'index' then the index is used.
    time_col : str (default='ds')
        Column that identifies each timestep, its values can be timestamps or integers.
    target_col : str (default='y')
        Column that contains the target.
    agg_by: List[str], optional (default=None)
        List of columns to aggregate the results.
        To get metrics per time series use [`id_col`].
    agg_fn: Callable, (default=np.mean)
        Function to aggregate metrics.
    engine: Any
        Engine to distributed computing.
    transform_kwargs: Any
        Extra arguments to pass to fugue's `transform`.
        
    Returns
    -------
    result : pandas DataFrame
        Metrics with one column per model.
    """
    if 'y' not in Y_hat_df.columns:
        raise Exception(
            'Please include the actual values in `Y_hat_df` '
            'or pass `Y_test_df`.'
        )
    df = Y_hat_df if Y_test_df is None else Y_hat_df.merge(Y_test_df, how='left', on=[id_col, time_col])
    transform_fn = partial(_cotransform, df2=Y_df) if Y_df is not None else transform   
    if Y_df is None:
        fn = _evaluate_without_insample
    else:
        fn = _evaluate
    has_cutoff = 'cutoff' in Y_hat_df.columns
    evaluation_df = transform_fn(
        df, 
        using=fn, 
        engine=engine, 
        params=dict(
            metrics=metrics,
            id_col=id_col,
            time_col=time_col,
            target_col=target_col,
            level=level,
        ), 
        schema=_schema_evaluate(
            df, 
            id_col=id_col, 
            time_col=time_col, 
            target_col=target_col,
        ), 
        partition=dict(by=id_col) if not has_cutoff else dict(by=[id_col, 'cutoff']),
    )
    if agg_by is not None:
        agg_by = ['metric'] + agg_by
    else:
        agg_by = ['metric']
    evaluation_df = transform(
        evaluation_df,
        using=_agg_evaluation,
        engine=engine,
        params=dict(agg_fn=agg_fn, agg_by=agg_by, id_col=id_col),
        schema=_schema_agg_evaluation(evaluation_df, agg_by, id_col=id_col),
        partition=agg_by,
        **transform_kwargs,
    )
    return evaluation_df
