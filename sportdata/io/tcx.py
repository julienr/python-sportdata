"""
This modules implements TCX files loading

The xml schema is available here :
    http://www8.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd

Inspired by https://github.com/vkurup/python-tcxparser
"""
from __future__ import print_function
from lxml import objectify
import dateutil.parser

TCX_NAMESPACE = 'http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2'


class TCXBase(object):
    def __init__(self, elm):
        self._elm = elm

    def xpath(self, query):
        return self._elm.xpath(query, namespaces={'ns': TCX_NAMESPACE})

    def find(self, what):
        return self._elm.find(what, namespaces={'ns': TCX_NAMESPACE})


class Trackpoint(TCXBase):
    def __init__(self, elm):
        super(Trackpoint, self).__init__(elm)
        self.time = dateutil.parser.parse(elm.Time.pyval)
        if self.find('ns:Position') is not None:
            self.latlng = (elm.Position.LatitudeDegrees.pyval,
                           elm.Position.LongitudeDegrees.pyval)
        else:
            self.latlng = None
        self.altitude = self.find('ns:AltitudeMeters')
        self.distance = self.find('ns:Distance')


class Lap(TCXBase):
    def __init__(self, elm):
        super(Lap, self).__init__(elm)
        self.start_time = dateutil.parser.parse(elm.attrib['StartTime'])
        self.duration = float(elm.TotalTimeSeconds.pyval)
        self.distance = float(elm.DistanceMeters.pyval)
        self.calories = float(elm.Calories.pyval)
        # Optional attributes
        self.max_speed = self.find('ns:MaximumSpeed')
        if self.find('ns:Track') is not None:
            self.trackpoints = [Trackpoint(e) for e in elm.Track.getchildren()]
        else:
            self.trackpoints = []

    def __repr__(self):
        return "Lap[dur=%d, dist=%d, max_speed=%d, cal=%d, %d points]" % (
            self.duration, self.distance, self.max_speed, self.calories,
            len(self.trackpoints))


class Activity(TCXBase):
    """Represent an Activity which consists of multiple laps"""
    def __init__(self, elm):
        super(Activity, self).__init__(elm)
        self.sport = elm.attrib['Sport']
        self.time = dateutil.parser.parse(elm.Id.pyval)
        self.laps = [Lap(e) for e in elm.Lap]


def load_activities(f):
    """
    Loads all the activities in the provided file-like object

    Returns:
        A list of :obj:`Activity` instance
    """
    base = TCXBase(objectify.parse(f))
    return [Activity(elm) for elm in base.xpath('//ns:Activity')]


def load_activity(f):
    """
    Shortcut for load_activities when there should be a single activity
    This will fail (with an assert) if there is not exactly 1 activity in the
    file.

    Returns:
        An :obj:`Activity` instance
    """
    activities = load_activities(f)
    assert len(activities) == 1
    return activities[0]
