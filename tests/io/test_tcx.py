import os
import sportdata.io.tcx as tcx
from numpy.testing import assert_allclose

DIR = os.path.dirname(__file__)


def test_load_activity1():
    fname = os.path.join(DIR, 'activity1.tcx')
    activity = tcx.load_activity(fname)
    assert len(activity.laps) == 2
    assert len(activity.laps[0].trackpoints) == 4
    assert len(activity.laps[1].trackpoints) == 3

    expected_latlng = (46.4635110553354, 6.844798419624567)
    assert_allclose(activity.laps[0].trackpoints[1].latlng, expected_latlng,
                    atol=1e-4)
