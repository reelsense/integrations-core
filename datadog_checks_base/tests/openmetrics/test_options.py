# (C) Datadog, Inc. 2020-present
# All rights reserved
# Licensed under a 3-clause BSD style license (see LICENSE)
import pytest

from ..utils import requires_py3
from .utils import get_check

pytestmark = [requires_py3, pytest.mark.openmetrics, pytest.mark.openmetrics_options]


class TestPrometheusEndpoint:
    def test_not_string(self, dd_run_check):
        check = get_check({'openmetrics_endpoint': 9000})

        with pytest.raises(Exception, match='^The setting `openmetrics_endpoint` must be a string$'):
            dd_run_check(check, extract_message=True)

    def test_missing(self, dd_run_check):
        check = get_check({'openmetrics_endpoint': ''})

        with pytest.raises(Exception, match='^The setting `openmetrics_endpoint` is required$'):
            dd_run_check(check, extract_message=True)
