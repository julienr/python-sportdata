"""
Garmin Connect (GC) downloader

Login flow reverse engineering taken from
https://github.com/kjkjava/garmin-connect-export/
"""
from __future__ import print_function
import requests
import logging
import json


GC_LOGIN_URL = 'https://sso.garmin.com/sso/login?service=https%3A%2F%2Fconnect.garmin.com%2Fpost-auth%2Flogin&webhost=olaxpw-connect04&source=https%3A%2F%2Fconnect.garmin.com%2Fen-US%2Fsignin&redirectAfterAccountLoginUrl=https%3A%2F%2Fconnect.garmin.com%2Fpost-auth%2Flogin&redirectAfterAccountCreationUrl=https%3A%2F%2Fconnect.garmin.com%2Fpost-auth%2Flogin&gauthHost=https%3A%2F%2Fsso.garmin.com%2Fsso&locale=en_US&id=gauth-widget&cssUrl=https%3A%2F%2Fstatic.garmincdn.com%2Fcom.garmin.connect%2Fui%2Fcss%2Fgauth-custom-v1.1-min.css&clientId=GarminConnect&rememberMeShown=true&rememberMeChecked=false&createAccountShown=true&openCreateAccount=false&usernameShown=false&displayNameShown=false&consumeServiceTicket=false&initialFocus=true&embedWidget=false&generateExtraServiceTicket=false'  # noqa

GC_POST_AUTH_URL = 'https://connect.garmin.com/post-auth/login?'

GC_SEARCH_URL = 'https://connect.garmin.com/proxy/activity-search-service-1.0/json/activities?'  # noqa

# There is a hard limit on the number of activities you can search for at
# a time
GC_ACTIVITIES_LIMIT = 100

class GCError(Exception):
    pass


class GarminConnectDownloader(object):
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.jar = requests.cookies.RequestsCookieJar()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36'  # noqa
        })
        self.logged_in = False

    def login(self, username, password):
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
            activities: A list of (activity_id, activity_name) tuple
            total_activities: The total number of activities available on
                the server (includes activities past start/limit)
        """
        data = self.search(start, limit)
        total_activities = int(data['results']['search']['totalFound'])
        activities = []
        for act in data['results']['activities']:
            activities.append((act['activity']['activityId'],
                               act['activity']['activityName']['value']))
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
            all_activities.append(activities)
            start += len(activities)
            if start >= total:
                break

        return all_activities

if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description='garmin connect downloader')
    parser.add_argument('username', type=str)
    parser.add_argument('password', type=str)

    args = parser.parse_args()

    downloader = GarminConnectDownloader()
    try:
        downloader.login(args.username, args.password)
        print("Logged in successfully")
        activities = downloader.get_all_activities()
        #data = downloader.search(0, 100)
        #with open('data.json', 'w') as f:
            #json.dump(data, f)
        #print('saved data')
    except GCError as e:
        print("Request failed :", e)
