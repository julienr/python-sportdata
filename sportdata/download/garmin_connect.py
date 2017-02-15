"""
Garmin Connect (GC) downloader

Login flow reverse engineering taken from
https://github.com/kjkjava/garmin-connect-export/

Example usage ::

    $ python sportdata/download/garmin_connect.py ../garmin_data \\
            --username=<username> \\
            --password=<password>

"""
from __future__ import print_function
import os
import json
import requests
import getpass
import logging


GC_LOGIN_URL = 'https://sso.garmin.com/sso/login?service=https%3A%2F%2Fconnect.garmin.com%2Fpost-auth%2Flogin&webhost=olaxpw-connect04&source=https%3A%2F%2Fconnect.garmin.com%2Fen-US%2Fsignin&redirectAfterAccountLoginUrl=https%3A%2F%2Fconnect.garmin.com%2Fpost-auth%2Flogin&redirectAfterAccountCreationUrl=https%3A%2F%2Fconnect.garmin.com%2Fpost-auth%2Flogin&gauthHost=https%3A%2F%2Fsso.garmin.com%2Fsso&locale=en_US&id=gauth-widget&cssUrl=https%3A%2F%2Fstatic.garmincdn.com%2Fcom.garmin.connect%2Fui%2Fcss%2Fgauth-custom-v1.1-min.css&clientId=GarminConnect&rememberMeShown=true&rememberMeChecked=false&createAccountShown=true&openCreateAccount=false&usernameShown=false&displayNameShown=false&consumeServiceTicket=false&initialFocus=true&embedWidget=false&generateExtraServiceTicket=false'  # noqa

GC_POST_AUTH_URL = 'https://connect.garmin.com/post-auth/login?'

GC_SEARCH_URL = 'https://connect.garmin.com/proxy/activity-search-service-1.0/json/activities?'  # noqa

GC_GPX_ACTIVITY = 'https://connect.garmin.com/modern/proxy/download-service/export/gpx/activity/'  # noqa
GC_TCX_ACTIVITY = 'https://connect.garmin.com/modern/proxy/download-service/export/tcx/activity/'  # noqa
GC_FIT_ACTIVITY = 'https://connect.garmin.com/proxy/download-service/files/activity/'  # noqa

# There is a hard limit on the number of activities you can search for at
# a time
GC_ACTIVITIES_LIMIT = 100


class GCError(Exception):
    pass


class GCFiletypeError(Exception):
    pass


class GarminConnectDownloader(object):
    """
    Class to login, list activities and download from Garmin Connect
    """
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.jar = requests.cookies.RequestsCookieJar()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36'  # noqa
        })
        self.logged_in = False

    def login(self, username, password):
        """Login to Garmin Connect"""
        # -- Step 1
        # Obtain session cookie (this is needed otherwise the POST below will
        # fail)
        r = self.session.get(GC_LOGIN_URL, cookies=self.jar)
        if r.status_code != 200:
            raise GCError('Non-200 status from GC auth step 1: %d'
                          % r.status_code)

        # -- Step 2
        # POST our login data (additional fields are required)
        post_data = {
            'username': username,
            'password': password,
            'embed': 'true',
            'lt': 'e1s1',
            '_eventId': 'submit',
            'displayNameRequired': 'false',
        }
        r = self.session.post(GC_LOGIN_URL, data=post_data)
        if r.status_code != 200:
            raise GCError('Non-200 status from GC auth step 2 %d'
                          % r.status_code)

        if 'CASTGC' not in self.session.cookies:
            raise GCError('Auth failed, couldn\'t find CASTGC cookie')
        # -- Step 3
        # Need to transform the CASTGC cookie in a login_ticket
        # Replace 'TGT-' with 'ST-0'
        login_ticket = 'ST-0' + self.session.cookies['CASTGC'][4:]
        r = self.session.get(GC_POST_AUTH_URL, params={'ticket': login_ticket})
        if r.status_code != 200:
            raise GCError('Non-200 status from GC auth step 3 %d'
                          % r.status_code)

        self.logged_in = True

    def search(self, start, limit=GC_ACTIVITIES_LIMIT):
        """
        Run a search on GC

        Returns:
            The raw json search response
        """
        assert limit <= GC_ACTIVITIES_LIMIT, "GC doesn't allow limit > 100"
        assert self.logged_in, "You must be logged_in to search()"
        r = self.session.get(GC_SEARCH_URL,
                             params={'start': start, 'limit': limit})
        if r.status_code != 200:
            raise GCError('Search failed with non-200 : %d'
                          % r.status_code)
        result = r.json()
        return result

    def get_activities(self, start, limit):
        """
        Obtain a list of activities

        Returns:
            A tuple (`activities`, `total_activities`). `activities` contains
            an array of JSON activity descriptions and `total_activites`
            contains the total number of activities available on the server
            (including activities outside of start/limit)
        """
        data = self.search(start, limit)
        total_activities = int(data['results']['search']['totalFound'])
        activities = data['results']['activities']
        return activities, total_activities

    def get_all_activities(self):
        """
        Helper method to get all activities, working around GC_ACTIVITIES_LIMIT

        Returns:
            activities: A list of (activity_id, activity_name) tuple
        """
        start = 0
        all_activities = []
        while True:
            activities, total = self.get_activities(start, GC_ACTIVITIES_LIMIT)
            self.logger.info('start=%d, total=%d, got %d activities' % (
                start, total, len(activities)))
            all_activities += activities
            start += len(activities)
            if start >= total:
                break

        return all_activities

    def download(self, activity_id, out_fname, filetype):
        """
        Download the specified activity to ``out_fname``

        Args:
            activity_id (str): The activity id
            out_fname (str): The filename where to download the data
            filetype (str): One of 'gpx', 'tcx' or 'fit'. The filetype to
                download. Note that although .fit is always available,
                GPX/TCX might not be available depending on activity

        Raises:
            GCFiletypeError: if the filetype is not available for this activity
            GCError: if another error occurs
        """
        assert filetype in ('gpx', 'tcx', 'fit')
        if filetype == 'gpx':
            download_url = GC_GPX_ACTIVITY + activity_id + '?full=true'
        elif filetype == 'tcx':
            download_url = GC_TCX_ACTIVITY + activity_id + '?full=true'
        else:
            download_url = GC_FIT_ACTIVITY + activity_id
        r = self.session.get(download_url, stream=True)

        if r.status_code == 204:
            # This indicates that this filetype is not available for this
            # activity
            raise GCFiletypeError('Filetype %s not available for %s' %
                                  (filetype, activity_id))

        if r.status_code != 200:
            raise GCError('Download failed with non-200 : %d' % r.status_code)

        with open(out_fname, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)

    def download_all(self, outdir, filetype, continue_on_fail=True):
        """
        Combines get_all_activities and download for each activity found
        This will skip activities that have already been downloaded
        In addition to the .`filetype` file, this will also create a .json
        file containing activity metadata

        Args:
            continue_on_fail: If True, will continue downloading other
                activities even if download for one activity fails

        Returns:
            n_downloaded, n_skipped, n_error
        """
        assert os.path.exists(outdir), 'Directory %s doesn\'t exist' % outdir
        n_downloaded = 0
        n_skipped = 0
        n_error = 0
        activities = downloader.get_all_activities()

        self.logger.info('%d activities found' % len(activities))
        for act in activities:
            act_id = act['activity']['activityId']
            act_name = act['activity']['activityName']['value']
            filename = os.path.join(outdir,
                                    'activity_%s.%s' % (act_id, filetype))
            json_filename = os.path.join(outdir, 'activity_%s.json' % act_id)
            if not os.path.exists(json_filename):
                self.logger.info('Saving %s' % json_filename)
                with open(json_filename, 'w') as f:
                    json.dump(act, f)

            if os.path.exists(filename):
                self.logger.info('Skipping %s - %s already exists' %
                                 (act_id, act_name))
                n_skipped += 1
                continue
            self.logger.info('Downloading %s(%s) to %s' %
                             (act_id, act_name, filename))
            try:
                self.download(act_id, filename, filetype)
                n_downloaded += 1
            except (GCError, GCFiletypeError) as e:
                n_error += 1
                if continue_on_fail:
                    self.logger.exception('Failed to download %s' % act_id)
                else:
                    raise e
        self.logger.info('Downloaded %d, skipped %d, %d errors' %
                         (n_downloaded, n_skipped, n_error))
        return n_downloaded, n_skipped, n_error

if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description='garmin connect downloader')
    parser.add_argument('outdir', type=str)
    parser.add_argument('--username', type=str, default=None)
    parser.add_argument('--password', type=str, default=None)

    args = parser.parse_args()

    if args.username is None:
        username = raw_input('garmin connect username :')
    else:
        username = args.username

    if args.password is None:
        password = getpass('garmin connect password :')
    else:
        password = args.password
    outdir = args.outdir

    downloader = GarminConnectDownloader()
    try:
        downloader.login(args.username, args.password)
        downloader.download_all(outdir, 'tcx')
    except GCError as e:
        print("Request failed :", e)
