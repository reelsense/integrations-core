# (C) Datadog, Inc. 2020-present
# All rights reserved
# Licensed under a 3-clause BSD style license (see LICENSE)
import re
from copy import deepcopy

from six import raise_from

from ....config import is_affirmative
from . import transformers

DEFAULT_METRIC_TYPE = 'native'


class MetricTransformer(object):
    def __init__(self, check, config):
        self.check = check
        self.logger = check.log
        self.cache_metric_wildcards = is_affirmative(config.get('cache_metric_wildcards', True))
        self.histogram_buckets_as_distributions = is_affirmative(
            config.get('histogram_buckets_as_distributions', False)
        )
        self.collect_histogram_buckets = self.histogram_buckets_as_distributions or is_affirmative(
            config.get('collect_histogram_buckets', True)
        )
        self.non_cumulative_histogram_buckets = self.histogram_buckets_as_distributions or is_affirmative(
            config.get('non_cumulative_histogram_buckets', False)
        )

        # Accessible to every transformer
        self.global_options = {
            'collect_histogram_buckets': self.collect_histogram_buckets,
            'histogram_buckets_as_distributions': self.histogram_buckets_as_distributions,
            'non_cumulative_histogram_buckets': self.non_cumulative_histogram_buckets,
        }

        metrics = config.get('metrics', [])
        if not isinstance(metrics, list):
            raise TypeError('Setting `metrics` must be an array')

        metrics_config = {}
        for i, entry in enumerate(metrics, 1):
            if isinstance(entry, str):
                metrics_config[entry] = {'name': entry, 'type': DEFAULT_METRIC_TYPE}
            elif isinstance(entry, dict):
                for key, value in entry.items():
                    if isinstance(value, str):
                        metrics_config[key] = {'name': value, 'type': DEFAULT_METRIC_TYPE}
                    elif isinstance(value, dict):
                        metrics_config[key] = value.copy()
                        metrics_config[key].setdefault('name', key)
                        metrics_config[key].setdefault('type', DEFAULT_METRIC_TYPE)
                    else:
                        raise TypeError(f'Value of entry `{key}` of setting `metrics` must be a string or a mapping')
            else:
                raise TypeError(f'Entry #{i} of setting `metrics` must be a string or a mapping')

        metrics_config = deepcopy(metrics_config)

        self.transformer_data = {}
        self.metric_patterns = []
        for raw_metric_name, config in metrics_config.items():
            escaped_metric_name = re.escape(raw_metric_name)

            if raw_metric_name != escaped_metric_name:
                self.metric_patterns.append(re.compile(raw_metric_name))
            else:
                try:
                    self.transformer_data[raw_metric_name] = self.compile_transformer(config)
                except Exception as e:
                    error = f'Error compiling transformer for metric `{raw_metric_name}`: {e}'
                    raise_from(type(e)(error), None)

    def get(self, metric):
        metric_name = metric.name

        transformer_data = self.transformer_data.get(metric_name)
        if transformer_data is not None:
            metric_type, transformer = transformer_data
            if metric_type == DEFAULT_METRIC_TYPE and self.skip_native_metric(metric):
                return

            return transformer
        elif self.metric_patterns:
            for metric_pattern in self.metric_patterns:
                if metric_pattern.search(metric_name):
                    metric_type, transformer = self.compile_transformer(
                        {'name': metric_name, 'type': DEFAULT_METRIC_TYPE}
                    )
                    if self.cache_metric_wildcards:
                        self.transformer_data[metric_name] = metric_type, transformer

                    if metric_type == DEFAULT_METRIC_TYPE and self.skip_native_metric(metric):
                        return

                    return transformer

        self.logger.debug('Skipping metric `%s` as it is not defined in `metrics`', metric_name)

    def compile_transformer(self, config):
        metric_name = config.pop('name')
        if not isinstance(metric_name, str):
            raise TypeError('field `name` must be a string')

        metric_type = config.pop('type')
        if not isinstance(metric_type, str):
            raise TypeError('field `type` must be a string')

        factory = TRANSFORMERS.get(metric_type)
        if factory is None:
            raise ValueError(f'unknown type `{metric_type}`')

        return metric_type, factory(self.check, metric_name, config, self.global_options)

    def skip_native_metric(self, metric):
        if metric.type == 'unknown':
            self.logger.debug('Metric `%s` has no type, so you must define one in the `metrics` setting', metric.name)
            return True
        elif metric.type not in NATIVE_TRANSFORMERS:
            self.logger.debug('Metric `%s` has unsupported type `%s`', metric.name, metric.type)
            return True

        return False


def get_native_transformer(check, metric_name, modifiers, global_options):
    """
    Uses whatever the endpoint describes as the metric type.
    """
    transformer = None

    def native(metric, sample_data, runtime_data):
        nonlocal transformer
        if transformer is None:
            transformer = NATIVE_TRANSFORMERS[metric.type](check, metric_name, modifiers, global_options)

        transformer(metric, sample_data, runtime_data)

    return native


# https://prometheus.io/docs/concepts/metric_types/
NATIVE_TRANSFORMERS = {
    'counter': transformers.get_counter,
    'gauge': transformers.get_gauge,
    'histogram': transformers.get_histogram,
    'summary': transformers.get_summary,
}

TRANSFORMERS = {
    'counter_gauge': transformers.get_counter_gauge,
    'metadata': transformers.get_metadata,
    'native': get_native_transformer,
    'service_check': transformers.get_service_check,
    'temporal_percent': transformers.get_temporal_percent,
    'time_elapsed': transformers.get_time_elapsed,
}
TRANSFORMERS.update(NATIVE_TRANSFORMERS)


# For documentation generation
class Transformers(object):
    pass


for transformer_name, transformer_factory in sorted(TRANSFORMERS.items()):
    setattr(Transformers, transformer_name, transformer_factory)
