# -*- coding: utf-8 -*-
# Background service: reports playback of this add-on's files to the server
# (POST <server>/api/state/<file id>), which keeps watched state and resume points
# for every app (e.g. the SKLK TV app); listings come back with that state.
# (Kodi's own earlier history: see history.py.)

import json
import re
import time
import urllib.request

import xbmc
import xbmcaddon
import xbmcgui

ADDON_ID = xbmcaddon.Addon().getAddonInfo('id')
FILE_ID = re.compile(r'all/play/(\d+)')
REPORT_EVERY = 30  # seconds, while playing
REPORT_TIMEOUT = 10  # seconds
CLIENT = 'kodi'
# home window property, set (to the time it started) while the last report of a
# playback is on its way, see wait_for_report()
REPORTING = ADDON_ID + '.reporting'
REPORT_WAIT = 3  # seconds, the most a listing waits for it


def log(message, level=xbmc.LOGINFO):
    xbmc.log('[{0} service] {1}'.format(ADDON_ID, message), level)


def server_url():
    """The server setting (see main.py), read each time since it may change."""
    return re.sub(r'/api$', '', xbmcaddon.Addon().getSetting('api_url').strip().rstrip('/'))


def report(file_id, position, duration, event, at=None):
    """
    Positions in seconds; at (ms since epoch) only for late reports.
    True if the server got it (an answer that it doesn't know the file counts too).
    """
    if not server_url():
        return False
    payload = {'position': position, 'event': event, 'client': CLIENT}
    if duration:
        payload['duration'] = duration
    if at:
        payload['at'] = at
    request = urllib.request.Request(
        server_url() + '/api/state/' + str(file_id),
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'Authorization': xbmcaddon.Addon().getSetting('auth_key')},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=REPORT_TIMEOUT) as response:
            response.read()
        return True
    except Exception as e:
        log('report failed: {0}'.format(e), xbmc.LOGWARNING)
        return False


def is_ours(url):
    """Streams of this add-on's server (as opposed to other add-ons, or LRT streams)."""
    server = server_url()
    return bool(server) and url.startswith(server + '/')


def reporting():
    """True while the service sends the last report of a playback."""
    try:
        started = float(xbmcgui.Window(10000).getProperty(REPORTING))
    except ValueError:
        return False
    # an older one: the service went away before clearing it
    return time.time() - started < REPORT_TIMEOUT + 5


def wait_for_report():
    """
    Before a listing (main.py): lets the last report of a playback that just
    ended reach the server first, for at most REPORT_WAIT seconds.

    Kodi reloads the list itself when it leaves the player, which then shows
    the new resume point (Continue watching: the next episode). No
    Container.Refresh from here for that: it would run while Kodi's own reload
    is still going, and the two loads of the plugin get mixed up, so Kodi
    loses the list (drops to the parent folder or the Videos root).
    """
    monitor = xbmc.Monitor()
    deadline = time.time() + REPORT_WAIT
    while reporting() and time.time() < deadline:
        if monitor.waitForAbort(0.1):
            break


class Player(xbmc.Player):
    def __init__(self):
        super().__init__()
        self.file_id = None
        self.position = 0
        self.duration = 0
        self.last_report = 0
        # (file_id, position, duration, event, at): retried until it goes through
        self.unsent = None

    def onAVStarted(self):
        self.finish('stop')  # in case another file was playing
        try:
            url = self.getPlayingFile()
        except RuntimeError:
            return
        match = FILE_ID.search(url) if is_ours(url) else None
        if match is None:
            return
        self.file_id = int(match.group(1))
        self.position = 0
        self.duration = 0
        self.update()
        self.send('start')

    def onPlayBackPaused(self):
        if self.file_id is not None:
            self.update()
            self.send('pause')

    def onPlayBackStopped(self):
        self.finish('stop')

    def onPlayBackEnded(self):
        self.finish('end')

    def onPlayBackError(self):
        self.finish('stop')

    def tick(self):
        """Every second, from the service loop."""
        if self.unsent and time.time() - self.last_report >= REPORT_EVERY:
            self.last_report = time.time()
            if report(*self.unsent):
                self.unsent = None

        if self.file_id is None:
            return
        self.update()
        if time.time() - self.last_report >= REPORT_EVERY and not xbmc.getCondVisibility('Player.Paused'):
            self.send('tick')

    def update(self):
        # after a stop there's no time to ask for, the last one known is reported
        try:
            if self.isPlayingVideo():
                self.position = self.getTime()
                self.duration = self.getTotalTime() or self.duration
        except RuntimeError:
            pass

    def finish(self, event):
        if self.file_id is None:
            return
        if event == 'end':
            self.position = self.duration
        # the list Kodi reloads now waits for it (wait_for_report)
        home = xbmcgui.Window(10000)
        home.setProperty(REPORTING, str(time.time()))
        try:
            self.send(event)
        finally:
            home.clearProperty(REPORTING)
        self.file_id = None

    def send(self, event):
        self.last_report = time.time()
        args = (self.file_id, self.position, self.duration, event)
        if report(*args):
            if self.unsent and self.unsent[0] == self.file_id:
                self.unsent = None
        else:
            self.unsent = args + (int(time.time() * 1000),)


def run():
    monitor = xbmc.Monitor()
    player = Player()
    while not monitor.waitForAbort(1):
        player.tick()


if __name__ == '__main__':
    run()
